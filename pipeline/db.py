"""Paths, the SQL renderer and DuckDB connections shared by every pipeline script."""

import os
import re
import subprocess
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
SQL = REPO / "sql"

DATASETS = [
    "bronze/recording",
    "bronze/electrode",
    "bronze/event",
    "bronze/ingest_audit",
    "silver/subject",
    "silver/record",
    "silver/recording",
    "silver/electrode",
    "silver/event",
    "gold/channel_quality",
    "gold/experiment_summary",
    "gold/feature_window",
    "gold/evidence",
]

# Datasets the lineage macros reference. A typed empty view stands in before they are written.
EMPTY = {
    "bronze/recording": (
        "experiment VARCHAR, subject_src VARCHAR, run SMALLINT, channel_idx SMALLINT, "
        "sample_idx INTEGER, value_raw FLOAT, ingest_id VARCHAR, lid UUID"
    ),
    "bronze/ingest_audit": (
        "ingest_id VARCHAR, source_path VARCHAR, source_url VARCHAR, sha256 VARCHAR, "
        "bytes BIGINT, sample_rate_hz INTEGER, rows_written BIGINT, tool VARCHAR, "
        "tool_version VARCHAR, duckdb_version VARCHAR, ingested_at TIMESTAMP"
    ),
    "silver/record": (
        "lid UUID, experiment VARCHAR, subject_pid VARCHAR, run SMALLINT, channel_idx SMALLINT, "
        "n_samples_src BIGINT"
    ),
}


def data_dir() -> Path:
    """Root for raw, bronze, silver, gold and keyring.duckdb. Never inside the repository."""
    return Path(os.environ.get("DATA_DIR", Path.home() / "data" / "ecog-lakehouse"))


def view_name(dataset: str) -> str:
    """`silver/recording` is the view `silver_recording`."""
    return dataset.replace("/", "_")


def render(sql: str, **values) -> str:
    """Replace every `{{name}}` with its value. An unknown name is an error, not an empty string."""

    def one(match):
        name = match.group(1)
        if name not in values:
            raise KeyError(f"placeholder {{{{{name}}}}} has no value, pass {name}=...")
        return str(values[name])

    return re.sub(r"\{\{(\w+)\}\}", one, sql)


def run_sql(con, path: Path, **values):
    """Render one SQL file and execute all its statements."""
    con.execute(render(path.read_text(encoding="utf-8"), **values))


def views(con):
    """One view per dataset that exists on disk, a typed empty view for the ones macros need."""
    for dataset in DATASETS:
        root = data_dir() / dataset
        if any(root.rglob("*.parquet")):
            con.execute(
                f"CREATE OR REPLACE VIEW {view_name(dataset)} AS SELECT * FROM read_parquet("
                f"'{root.as_posix()}/**/*.parquet', hive_partitioning = true, "
                "hive_types_autocast = false)"
            )
        elif dataset in EMPTY:
            cols = ", ".join(
                f"NULL::{t} AS {c}" for c, t in (p.split() for p in EMPTY[dataset].split(", "))
            )
            con.execute(f"CREATE OR REPLACE VIEW {view_name(dataset)} AS SELECT {cols} WHERE false")


def connect(database: str = ":memory:"):
    """A connection with every dataset view and the lineage macros loaded."""
    con = duckdb.connect(database)
    views(con)
    run_sql(con, SQL / "lineage.sql")
    return con


def git_commit() -> str:
    """Current commit hash, or `unknown` outside a git checkout."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or "unknown"
