"""Build one layer: `run.py bronze [--synth] | silver | gold`.

Bronze converts raw files through convert_mat.py. Silver and Gold render and execute the SQL
files of `sql/<layer>/` in name order; each file writes one dataset.
"""

import argparse
import shutil
import sys

from pipeline import convert_mat, db, keyring, line_noise, manifest, synth


def run_files(con, paths, **values):
    """Render and execute SQL files in order, refreshing the dataset views after each."""
    for path in paths:
        print(f"run: {path.parent.name}/{path.name}")
        db.run_sql(con, path, data_dir=db.data_dir().as_posix(), **values)
        db.views(con)


def layer_files(layer: str):
    for dataset in db.DATASETS:
        if dataset.startswith(layer + "/"):
            (db.data_dir() / dataset).mkdir(parents=True, exist_ok=True)
    return sorted((db.SQL / layer).glob("*.sql"))


def bronze(use_synth: bool) -> int:
    """Synthetic set when asked or when raw/ holds no real experiment; otherwise only the
    canary subject of each real experiment is generated (spec 12.5), then everything converts."""
    raw = db.data_dir() / "raw"
    real = sorted(
        d.name for d in (raw.iterdir() if raw.exists() else [])
        if d.is_dir() and d.name != "synthetic" and d.name in convert_mat.ADAPTERS
    )
    synth.main([] if use_synth or not real else ["--canary", *real])
    return convert_mat.main([])


def silver() -> int:
    con = db.connect()
    codes = [r[0] for r in con.execute("SELECT DISTINCT subject_src FROM bronze_recording").fetchall()]
    print(f"run: keyring, {keyring.pseudonymise(codes)} new pseudonyms")
    con.execute(f"ATTACH '{keyring.path().as_posix()}' AS keyring (READ_ONLY)")
    units = ", ".join(f"('{e}', {u})" for e, u in convert_mat.UV_PER_UNIT.items())
    files = layer_files("silver")
    recording = db.SQL / "silver" / "030_recording.sql"
    run_files(con, [f for f in files if f < recording], unit_scale_values=units)
    # One plain COPY per partition keeps the sort order, see the note in 030_recording.sql.
    target = db.data_dir() / "silver" / "recording"
    shutil.rmtree(target)
    partitions = con.execute(
        "SELECT DISTINCT experiment, subject_pid FROM silver_record ORDER BY 1, 2"
    ).fetchall()
    for experiment, subject_pid in partitions:
        (target / f"experiment={experiment}" / f"subject_pid={subject_pid}").mkdir(parents=True)
        db.run_sql(
            con,
            recording,
            data_dir=db.data_dir().as_posix(),
            unit_scale_values=units,
            experiment=experiment,
            subject_pid=subject_pid,
        )
    print(f"run: silver/{recording.name}, {len(partitions)} partitions")
    db.views(con)
    run_files(con, [f for f in files if f > recording], unit_scale_values=units)
    return 0


def gold() -> int:
    con = db.connect()
    print(f"run: line noise on {line_noise.register(con)} records")
    run_files(con, layer_files("gold"))
    print(f"run: gold/dataset_manifest, {manifest.write(con)} datasets")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("layer", choices=["bronze", "silver", "gold"])
    parser.add_argument("--synth", action="store_true", help="generate synthetic raw files first")
    args = parser.parse_args(argv)
    if args.layer == "bronze":
        return bronze(args.synth)
    if args.layer == "silver":
        return silver()
    return gold()


if __name__ == "__main__":
    sys.exit(main())
