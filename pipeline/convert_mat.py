"""Convert raw recordings to Bronze, one adapter per directory under raw/.

An adapter turns one source file into a `Source`. The registry maps the directory name
under `raw/` to the adapter; a directory without one is skipped with a logged reason.
Each converted file appends one `bronze/ingest_audit` row. A file whose sha256 is already
in the audit is skipped, so a rerun is a no-op and Bronze partitions are never rewritten.
"""

import hashlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
from scipy.io import loadmat

from pipeline import db, keyring
from pipeline.lid import ulid

TOOL = "convert_mat.py"

# Microvolts per raw amplifier unit, per experiment. Silver applies it; Bronze stays raw.
# Stanford values come from each experiment's README_<experiment>_dataset_notes.
UV_PER_UNIT = {"fingerflex": 0.0298, "motor_basic": 0.0298, "faces_basic": 0.0298}

STANFORD_URL = "https://stacks.stanford.edu/file/druid:zk881ps0522/{experiment}.zip"
STANFORD_SAMPLE_RATE_HZ = 1000  # manuscript, Methods: "sampled at 1000 Hz", every experiment

# elec_regions codes, README_fingerflex_dataset_notes. Codes outside the table are NULL.
FINGERFLEX_REGIONS = {
    1: "dorsal M1",
    3: "dorsal S1",
    4: "ventral sensorimotor",
    6: "frontal",
    7: "parietal",
    8: "temporal",
    9: "occipital",
}
FINGERFLEX_LABELS = {1: "thumb", 2: "index", 3: "middle", 4: "ring", 5: "little"}
# stim codes, README_motor_basic_dataset_notes. Two files also carry 13 and 15, undocumented,
# kept as events with a NULL label.
MOTOR_BASIC_LABELS = {11: "tongue", 12: "hand"}
# stim codes, README_faces_basic_dataset_notes: 1 to 50 a house, 51 to 100 a face, 101 the
# interstimulus interval (mapped to 0, no event), 0 outside the task.
FACES_BASIC_LABELS = {**{c: "house" for c in range(1, 51)}, **{c: "face" for c in range(51, 101)}}
FACES_BASIC_ISI = 101
# elcode labels, faces_basic/fhpred_master.m area_lbls (Destrieux et al. 2010). 15 to 19 are
# blank there and 20 is "Non-included area"; both are NULL here.
FACES_BASIC_REGIONS = {
    1: "temporal pole",
    2: "parahippocampal gyrus",
    3: "inferior temporal gyrus",
    4: "middle temporal gyrus",
    5: "fusiform gyrus",
    6: "lingual gyrus",
    7: "inferior occipital gyrus",
    8: "cuneus",
    9: "posterior ventral cingulate gyrus",
    10: "middle occipital gyrus",
    11: "occipital pole",
    12: "precuneus",
    13: "superior occipital gyrus",
    14: "posterior dorsal cingulate gyrus",
}

# Source codes of the canary subjects, spec 12.5. Their records carry the radioactive bit
# from Bronze on, so no copy of a record can lose it.
CANARY_SUBJECTS = {"canary"}

SYNTHETIC_LABELS = {
    "fingerflex": {1: "thumb", 2: "index", 3: "middle", 4: "ring", 5: "little"},
    "motor_basic": {1: "hand", 2: "tongue"},
    "faces_basic": {1: "house", 2: "face"},
}


@dataclass
class Source:
    """One source file as the Bronze writer needs it."""

    experiment: str
    subject_src: str
    run: int
    sample_rate_hz: int
    source_url: str
    data: np.ndarray  # samples x channels, raw amplifier units
    stim: np.ndarray  # one cue code per sample, 0 when none
    locs: np.ndarray | None  # channels x 3, mm
    brain_area: list[str] | None
    labels: dict[int, str]


def read_synthetic(path: Path) -> Source:
    """Adapter for files written by pipeline/synth.py."""
    m = loadmat(path, simplify_cells=True)
    experiment = str(m["experiment"])
    return Source(
        experiment=experiment,
        subject_src=str(m["subject"]),
        run=int(m["run"]),
        sample_rate_hz=int(m["srate"]),
        source_url=f"synthetic://{experiment}/{path.name}",
        data=np.asarray(m["data"], dtype=np.float32),
        stim=np.asarray(m["stim"]).reshape(-1),
        locs=np.asarray(m["locs"], dtype=np.float32),
        brain_area=[str(a) for a in m["brain_area"]],
        labels=SYNTHETIC_LABELS.get(experiment, {}),
    )


def read_fingerflex(path: Path) -> Source:
    """Stanford `fingerflex`, one file per subject at `data/<code>/<code>_fingerflex.mat`.

    | Bronze | Source | From |
    |---|---|---|
    | subject_src | file name prefix | README says a `subject` variable, the files carry none |
    | run | 1 | one file per subject |
    | sample_rate_hz | 1000 | README, "sampled at 1000Hz" |
    | value_raw | `data` (time x channels, int32) | README, 1 unit = 0.0298 microvolts |
    | event | `cue` (time x 1), 0 rest, 1 thumb to 5 little | README; `<code>_stim.mat` is the behaviour, not the cue, unused |
    | x_mm, y_mm, z_mm | `locs` (channels x 3) | README |
    | brain_area | `elec_regions` code through FINGERFLEX_REGIONS | README table |
    """
    m = loadmat(path, simplify_cells=True, variable_names=["data", "cue", "locs", "elec_regions"])
    return Source(
        experiment="fingerflex",
        subject_src=path.name.split("_")[0],
        run=1,
        sample_rate_hz=STANFORD_SAMPLE_RATE_HZ,
        source_url=STANFORD_URL.format(experiment="fingerflex"),
        data=np.asarray(m["data"], dtype=np.float32),
        stim=np.asarray(m["cue"]).reshape(-1).astype(np.int16),
        locs=np.asarray(m["locs"], dtype=np.float32),
        brain_area=[FINGERFLEX_REGIONS.get(int(c)) for c in np.asarray(m["elec_regions"]).reshape(-1)],
        labels=FINGERFLEX_LABELS,
    )


def read_motor_basic(path: Path) -> Source:
    """Stanford `motor_basic`, one file per subject at `data/<code>_mot_t_h.mat`.

    | Bronze | Source | From |
    |---|---|---|
    | subject_src | file name prefix | README |
    | run | 1 | one file per subject |
    | sample_rate_hz | 1000 | README, "sampled at 1000Hz" |
    | value_raw | `data` (time x channels, int16 or int32) | README, 1 unit = 0.0298 microvolts |
    | event | `stim` (time x 1), 0 blank, 11 tongue, 12 hand | README |
    | x_mm, y_mm, z_mm | `electrodes` (channels x 3) in `locs/<code>_electrodes.mat`, Talairach | README |
    | brain_area | NULL | the files carry no region code |
    """
    code = path.name.split("_")[0]
    m = loadmat(path, simplify_cells=True)
    locs = loadmat(path.parent.parent / "locs" / f"{code}_electrodes.mat", simplify_cells=True)
    return Source(
        experiment="motor_basic",
        subject_src=code,
        run=1,
        sample_rate_hz=STANFORD_SAMPLE_RATE_HZ,
        source_url=STANFORD_URL.format(experiment="motor_basic"),
        data=np.asarray(m["data"], dtype=np.float32),
        stim=np.asarray(m["stim"]).reshape(-1).astype(np.int16),
        locs=np.asarray(locs["electrodes"], dtype=np.float32),
        brain_area=None,
        labels=MOTOR_BASIC_LABELS,
    )


def read_faces_basic(path: Path) -> Source:
    """Stanford `faces_basic`, one file per subject at `data/<code>/<code>_faceshouses.mat`.

    | Bronze | Source | From |
    |---|---|---|
    | subject_src | file name prefix | README |
    | run | 1 | one file per subject |
    | sample_rate_hz | `srate` | the file, 1000 in all of them |
    | value_raw | `data` (time x channels, float64 of integer amplifier units) | README gives no scale; UV_PER_UNIT takes the 0.0298 of the other two READMEs, same amplifiers and settings (manuscript, Methods) |
    | event | `stim` (time x 1), 1 to 50 house, 51 to 100 face, 101 interstimulus | README; 101 is not an event |
    | x_mm, y_mm, z_mm | NULL | `locs/<code>_xslocs.mat` holds MRI voxel indices, not millimetres |
    | brain_area | `elcode` in `locs/<code>_xslocs.mat` through FACES_BASIC_REGIONS | fhpred_master.m area_lbls |
    """
    code = path.name.split("_")[0]
    m = loadmat(path, simplify_cells=True)
    locs = loadmat(path.parent.parent.parent / "locs" / f"{code}_xslocs.mat", simplify_cells=True)
    stim = np.asarray(m["stim"]).reshape(-1).astype(np.int16)
    stim[stim == FACES_BASIC_ISI] = 0
    return Source(
        experiment="faces_basic",
        subject_src=code,
        run=1,
        sample_rate_hz=int(m["srate"]),
        source_url=STANFORD_URL.format(experiment="faces_basic"),
        data=np.asarray(m["data"], dtype=np.float32),
        stim=stim,
        locs=None,
        brain_area=[FACES_BASIC_REGIONS.get(int(c)) for c in np.asarray(locs["elcode"]).reshape(-1)],
        labels=FACES_BASIC_LABELS,
    )


# Directory under raw/ to (reader, glob of the data files inside that directory).
ADAPTERS = {
    "synthetic": (read_synthetic, "*/*.mat"),
    "fingerflex": (read_fingerflex, "*/data/*/*_fingerflex.mat"),
    "motor_basic": (read_motor_basic, "*/data/*_mot_t_h.mat"),
    "faces_basic": (read_faces_basic, "*/data/*/*_faceshouses.mat"),
}


def stage(con, src: Source):
    """Register the source arrays as relations the Bronze SQL reads."""
    n, ch = src.data.shape
    con.register(
        "src_recording",
        {
            "channel_idx": np.repeat(np.arange(ch, dtype=np.int16), n),
            "sample_idx": np.tile(np.arange(n, dtype=np.int32), ch),
            "value_raw": np.ascontiguousarray(src.data.T).reshape(-1),
        },
    )
    previous = np.concatenate(([0], src.stim[:-1]))
    onsets = np.flatnonzero((src.stim != 0) & (src.stim != previous))
    con.register(
        "src_event",
        {"sample_idx": onsets.astype(np.int32), "event_code": src.stim[onsets].astype(np.int16)},
    )
    con.execute("CREATE OR REPLACE TEMP TABLE src_label (event_code SMALLINT, event_label VARCHAR)")
    con.executemany("INSERT INTO src_label VALUES (?, ?)", list(src.labels.items()) or [(None, None)])
    con.execute(
        "CREATE OR REPLACE TEMP TABLE src_electrode "
        "(channel_idx SMALLINT, x_mm FLOAT, y_mm FLOAT, z_mm FLOAT, brain_area VARCHAR)"
    )
    con.executemany(
        "INSERT INTO src_electrode VALUES (?, ?, ?, ?, ?)",
        [
            (
                c,
                *([float(v) for v in src.locs[c]] if src.locs is not None else [None] * 3),
                src.brain_area[c] if src.brain_area is not None else None,
            )
            for c in range(ch)
        ],
    )


def convert(con, path: Path, adapter) -> int:
    """Write one file to Bronze. Returns rows written to bronze/recording, 0 when skipped."""
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if con.execute("SELECT count(*) FROM bronze_ingest_audit WHERE sha256 = ?", [sha256]).fetchone()[0]:
        print(f"convert: skip {path}, sha256 already ingested")
        return 0
    with path.open("rb") as f:
        if b"MATLAB 7.3" in f.read(128):
            print(f"convert: skip {path}, MATLAB v7.3 is HDF5 and needs h5py, see ADR-0005")
            return 0
    src = adapter(path)
    code = con.execute(
        "SELECT code FROM lineage_experiment WHERE experiment = ?", [src.experiment]
    ).fetchone()
    if code is None:
        print(f"convert: skip {path}, experiment '{src.experiment}' has no lineage code")
        return 0
    stage(con, src)
    for name in ("recording", "electrode", "event", "ingest_audit"):
        (db.data_dir() / "bronze" / name).mkdir(parents=True, exist_ok=True)
    values = {
        "data_dir": db.data_dir().as_posix(),
        "experiment": src.experiment,
        "experiment_code": code[0],
        "subject_src": src.subject_src,
        "run": src.run,
        "radioactive": int(src.subject_src in CANARY_SUBJECTS),
        "ingest_id": ulid(),
        "ingest_ord": 1 + con.execute("SELECT count(*) FROM bronze_ingest_audit").fetchone()[0],
        "ingested_at": datetime.now(UTC).replace(tzinfo=None).isoformat(sep=" "),
    }
    for name in ("recording", "electrode", "event"):
        db.run_sql(con, db.SQL / "bronze" / f"{name}.sql", **values)
    rows = con.execute("SELECT count(*) FROM src_recording").fetchone()[0]
    # A source read from outside DATA_DIR has no path below it, so it keeps its absolute one
    # and hash_match will not find it, which is the honest answer for a file that is not here.
    root = db.data_dir()
    below = path.relative_to(root) if path.is_relative_to(root) else path
    db.run_sql(
        con,
        db.SQL / "bronze" / "ingest_audit.sql",
        source_path=path.as_posix(),
        source_path_rel=below.as_posix(),
        source_url=src.source_url,
        sha256=sha256,
        bytes=path.stat().st_size,
        sample_rate_hz=src.sample_rate_hz,
        rows_written=rows,
        tool=TOOL,
        tool_version=db.git_commit(),
        duckdb_version=duckdb.__version__,
        ingest_host=keyring.host(),
        **values,
    )
    db.views(con)
    print(f"convert: wrote {path} as {values['ingest_id']}, {rows} rows")
    return rows


def main(argv=None) -> int:
    raw = db.data_dir() / "raw"
    con = db.connect()
    total = 0
    for directory in sorted(p for p in raw.iterdir() if p.is_dir()) if raw.exists() else []:
        if directory.name not in ADAPTERS:
            print(f"convert: skip {directory}, no adapter registered for '{directory.name}'")
            continue
        adapter, pattern = ADAPTERS[directory.name]
        for path in sorted(directory.glob(pattern)):
            total += convert(con, path, adapter)
    print(f"convert: {total} rows written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
