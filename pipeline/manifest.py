"""gold/dataset_manifest, spec 3.3: one row per dataset of this build, the handle a model
registry or a submission package holds. Rewritten on every Gold build. dataset_version is the
digest gold/evidence uses; lid_lo and lid_hi bound the records; file_digests lists the sha256
of the source files those records came from.
"""

from datetime import UTC, datetime

from pipeline import db

LAYER = {"bronze": 1, "silver": 2, "gold": 3}
DATASET = "gold/dataset_manifest"


def row(con, dataset: str, produced_at, commit: str) -> tuple:
    view = db.view_name(dataset)
    columns = {r[0] for r in con.execute(f"DESCRIBE {view}").fetchall()}
    if "lid" in columns:
        n, lo, hi = con.execute(f"SELECT count(*), min(lid), max(lid) FROM {view}").fetchone()
        digests = con.execute(
            f"SELECT DISTINCT d.sha256 FROM (SELECT DISTINCT lid FROM {view} WHERE lid IS NOT NULL) v "
            "JOIN lineage_dim d ON d.ingest_ord = lid_file(lid_u128(v.lid)) ORDER BY 1"
        ).fetchall()
    else:
        n, lo, hi = con.execute(f"SELECT count(*) FROM {view}").fetchone()[0], None, None
        digests = con.execute("SELECT sha256 FROM lineage_dim ORDER BY 1").fetchall()
    layer = LAYER[dataset.split("/")[0]]
    return (db.dataset_version(dataset), dataset, layer, lo, hi, n, [d[0] for d in digests],
            produced_at, commit)


def write(con) -> int:
    """One row per dataset that exists on disk, this dataset excluded. Returns rows written."""
    produced_at = datetime.now(UTC).replace(tzinfo=None)
    commit = db.git_commit()
    rows = [
        row(con, d, produced_at, commit)
        for d in db.DATASETS
        if d != DATASET and any((db.data_dir() / d).rglob("*.parquet"))
    ]
    con.execute(f"CREATE OR REPLACE TEMP TABLE manifest_build ({db.columns(DATASET)})")
    con.executemany("INSERT INTO manifest_build VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    target = db.data_dir() / DATASET / "data_0.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY (SELECT * FROM manifest_build ORDER BY dataset) TO '{target.as_posix()}' (FORMAT parquet)")
    db.views(con)
    return len(rows)
