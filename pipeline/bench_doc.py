"""docs/bench.md: what the current DATA_DIR holds, per experiment, every number a query result.

Bronze counts leave the canary subjects out, so the table describes the source library.
Build wall clock is the span from the first ingestion of the audit to the last evidence
row, so it assumes one build per DATA_DIR and leaves fetch and publish out.
"""

import sys

from pipeline import convert_mat, db

OUT = db.REPO / "docs" / "bench.md"

TABLE = """
WITH files AS (
    SELECT layer, experiment, sum(bytes) AS bytes FROM build_files GROUP BY ALL
),
records AS (
    SELECT experiment, subject_src, run, channel_idx, count(*) AS samples
    FROM bronze_recording
    WHERE subject_src NOT IN (SELECT subject_src FROM canary)
    GROUP BY ALL
),
per_experiment AS (
    SELECT experiment,
           count(DISTINCT subject_src) AS subjects,
           count(DISTINCT (subject_src, run)) AS runs,
           count(*) AS channels,
           sum(samples) AS samples
    FROM records
    GROUP BY 1
)
SELECT e.experiment, e.subjects, e.runs, e.channels, e.samples, b.bytes AS bronze_bytes, s.bytes AS silver_bytes
FROM per_experiment e
LEFT JOIN files b ON b.layer = 'bronze' AND b.experiment = e.experiment
LEFT JOIN files s ON s.layer = 'silver' AND s.experiment = e.experiment
ORDER BY 1
"""

BUILD = """
SELECT
    (SELECT any_value(git_commit) FROM gold_dataset_manifest) AS git_commit,
    (SELECT any_value(duckdb_version) FROM bronze_ingest_audit) AS duckdb_version,
    (SELECT count(*) FROM bronze_ingest_audit) AS files,
    (SELECT max(ran_at) FROM gold_evidence) - (SELECT min(ingested_at) FROM bronze_ingest_audit) AS wall_clock
"""


def build_files():
    """(layer, experiment, bytes) per recording Parquet file, from the file system."""
    rows = []
    for layer in ("bronze", "silver"):
        for path in (db.data_dir() / layer / "recording").rglob("*.parquet"):
            experiment = next(p.split("=", 1)[1] for p in path.parts if p.startswith("experiment="))
            rows.append((layer, experiment, path.stat().st_size))
    return rows


def markdown(cur) -> str:
    cols = [d[0] for d in cur.description]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in cur.fetchall():
        lines.append("| " + " | ".join("NULL" if v is None else str(v) for v in row) + " |")
    return "\n".join(lines)


def main(argv=None) -> int:
    con = db.connect()
    con.execute("CREATE TEMP TABLE build_files (layer VARCHAR, experiment VARCHAR, bytes BIGINT)")
    con.executemany("INSERT INTO build_files VALUES (?, ?, ?)", build_files() or [(None, None, None)])
    con.execute("CREATE TEMP TABLE canary (subject_src VARCHAR)")
    con.executemany("INSERT INTO canary VALUES (?)", [(s,) for s in convert_mat.CANARY_SUBJECTS])
    commit, duckdb_version, files, wall_clock = con.execute(BUILD).fetchone()
    text = "\n".join([
        "# bench.md",
        "",
        (
            f"Counts of the build in `DATA_DIR`, written by `pipeline/bench_doc.py` at commit "
            f"`{commit}` with DuckDB {duckdb_version}. Canary subjects are left out. Bytes are "
            "the recording Parquet files of each layer."
        ),
        "",
        markdown(con.execute(TABLE)),
        "",
        f"Files ingested: {files}. Build wall clock, first ingestion to last evidence row: {wall_clock}.",
        "",
    ])
    OUT.write_text(text, encoding="utf-8")
    print(f"bench_doc: wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
