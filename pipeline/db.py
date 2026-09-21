"""Paths, the SQL renderer and DuckDB connections shared by every pipeline script."""

import hashlib
import os
import re
import subprocess
from pathlib import Path

import duckdb
import yaml

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
    "gold/dataset_manifest",
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


def columns(dataset: str) -> str | None:
    """`name TYPE, ...` of a dataset: inline for Bronze, from its contract for Silver and Gold."""
    if dataset in EMPTY:
        return EMPTY[dataset]
    contract = REPO / "contracts" / f"{view_name(dataset)}.yaml"
    if not contract.exists():
        return None
    props = yaml.safe_load(contract.read_text(encoding="utf-8"))["schema"][0]["properties"]
    return ", ".join(f"{p['name']} {p['physicalType']}" for p in props)


def views(con):
    """One view per dataset on disk; a typed empty view for a dataset with a known schema."""
    for dataset in DATASETS:
        root = data_dir() / dataset
        for aborted in (p for p in root.rglob("*.parquet") if p.stat().st_size == 0):
            print(f"db: removed {aborted}, an empty file left by an aborted write")
            aborted.unlink()
        if any(root.rglob("*.parquet")):
            con.execute(
                f"CREATE OR REPLACE VIEW {view_name(dataset)} AS SELECT * FROM read_parquet("
                f"'{root.as_posix()}/**/*.parquet', hive_partitioning = true, "
                "hive_types_autocast = false)"
            )
        elif (schema := columns(dataset)) is not None:
            cols = ", ".join(f"NULL::{t} AS {c}" for c, t in (p.split() for p in schema.split(", ")))
            con.execute(f"CREATE OR REPLACE VIEW {view_name(dataset)} AS SELECT {cols} WHERE false")
    published = REPO / "docs" / "data"
    if any(published.rglob("*.parquet")):
        con.execute(
            "CREATE OR REPLACE VIEW docs_data AS SELECT lid FROM read_parquet("
            f"'{published.as_posix()}/**/*.parquet', union_by_name = true)"
        )
    else:
        con.execute("CREATE OR REPLACE VIEW docs_data AS SELECT NULL::UUID AS lid WHERE false")


def connect(database: str = ":memory:"):
    """A connection with every dataset view and the lineage macros loaded: the generated
    macros first, then the hand written extras that build on them."""
    con = duckdb.connect(database)
    # Spill files belong under DATA_DIR, spec 7; the default is the working directory, the repo.
    (data_dir() / "tmp").mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{(data_dir() / 'tmp').as_posix()}'")
    # Every ORDER BY in sql/ is explicit; keeping arrival order across parallel joins held
    # 12 GB of Silver in memory on gold/channel_quality and failed on 871 million rows.
    con.execute("SET preserve_insertion_order = false")
    views(con)
    run_sql(con, SQL / "lineage" / "lid_generated.sql")
    run_sql(con, SQL / "lineage" / "lid_extras.sql")
    return con


def dataset_version(dataset: str) -> str:
    """sha256 of the sorted list of the dataset's Parquet file digests, spec 5.3."""
    files = (data_dir() / dataset).rglob("*.parquet")
    digests = sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in files)
    return hashlib.sha256("\n".join(digests).encode()).hexdigest()


def git_commit() -> str:
    """Current commit hash, or `unknown` outside a git checkout."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() or "unknown"
