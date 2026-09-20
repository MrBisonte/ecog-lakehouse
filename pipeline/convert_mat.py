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

from pipeline import db
from pipeline.lid import ulid

TOOL = "convert_mat.py"

# Microvolts per raw amplifier unit, per experiment. Silver applies it; Bronze stays raw.
UV_PER_UNIT = {"fingerflex": 0.1, "motor_basic": 0.1}

# Source codes of the canary subjects, spec 12.5. Their records carry the radioactive bit
# from Bronze on, so no copy of a record can lose it.
CANARY_SUBJECTS = {"canary"}

SYNTHETIC_LABELS = {
    "fingerflex": {1: "thumb", 2: "index", 3: "middle", 4: "ring", 5: "little"},
    "motor_basic": {1: "hand", 2: "tongue"},
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


ADAPTERS = {"synthetic": read_synthetic}


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
                *(float(v) for v in (src.locs[c] if src.locs is not None else (None,) * 3)),
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
    db.run_sql(
        con,
        db.SQL / "bronze" / "ingest_audit.sql",
        source_path=path.as_posix(),
        source_url=src.source_url,
        sha256=sha256,
        bytes=path.stat().st_size,
        sample_rate_hz=src.sample_rate_hz,
        rows_written=rows,
        tool=TOOL,
        tool_version=db.git_commit(),
        duckdb_version=duckdb.__version__,
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
        adapter = ADAPTERS.get(directory.name)
        if adapter is None:
            print(f"convert: skip {directory}, no adapter registered for '{directory.name}'")
            continue
        for path in sorted(directory.rglob("*.mat")):
            total += convert(con, path, adapter)
    print(f"convert: {total} rows written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
