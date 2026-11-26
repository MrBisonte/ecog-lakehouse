"""Paths, the SQL renderer and DuckDB connections shared by every pipeline script."""

import hashlib
import os
import re
import subprocess
from pathlib import Path

import duckdb
import yaml

from pipeline import settings

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
        "ingest_id VARCHAR, data_root VARCHAR, source_path_rel VARCHAR, "
        "source_url VARCHAR, sha256 VARCHAR, "
        "bytes BIGINT, sample_rate_hz INTEGER, rows_written BIGINT, tool VARCHAR, "
        "tool_version VARCHAR, duckdb_version VARCHAR, ingest_host VARCHAR, "
        "ingested_at TIMESTAMP"
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


def render(text: str, **values) -> str:
    """Replace every `{{name}}` with its value. An unknown name is an error, not an empty string."""

    def one(match):
        name = match.group(1)
        if name not in values:
            raise KeyError(f"placeholder {{{{{name}}}}} has no value, pass {name}=...")
        return str(values[name])

    return re.sub(r"\{\{(\w+)\}\}", one, text)


def run_sql(con, path: Path, **values):
    """Render one SQL file and execute all its statements."""
    con.execute(render(path.read_text(encoding="utf-8"), **values))


def contract_path(dataset: str) -> Path:
    """`gold/evidence` is declared by `contracts/gold_evidence.yaml`. Bronze has no contract."""
    return REPO / "contracts" / f"{view_name(dataset)}.yaml"


def contract_columns(dataset: str) -> list[tuple[str, str]] | None:
    """Name and physical type of each property of the dataset's contract, in the order of the
    contract. None for a dataset with no contract."""
    path = contract_path(dataset)
    if not path.exists():
        return None
    props = yaml.safe_load(path.read_text(encoding="utf-8"))["schema"][0]["properties"]
    return [(p["name"], p["physicalType"]) for p in props]


def column_list(declared: list[tuple[str, str]]) -> str:
    """`name TYPE, ...`, the text a CREATE TABLE takes between its brackets."""
    return ", ".join(f"{name} {kind}" for name, kind in declared)


def columns(dataset: str) -> str | None:
    """`name TYPE, ...` of a dataset: inline for Bronze, from its contract for Silver and Gold."""
    if dataset in EMPTY:
        return EMPTY[dataset]
    declared = contract_columns(dataset)
    return None if declared is None else column_list(declared)


def staging_columns(dataset: str, rows: list[dict]) -> list[tuple[str, str]]:
    """The columns of the contract that `rows` are staged under.

    Refused, each with the contract file named: a dataset with no contract, no rows, and the
    first row whose keys are not exactly the properties of the contract.
    """
    contract = contract_path(dataset).relative_to(REPO).as_posix()
    declared = contract_columns(dataset)
    if declared is None:
        raise ValueError(
            f"{dataset} has no contract to stage rows by, {contract} does not exist, every "
            "Silver and Gold dataset of db.DATASETS has one"
        )
    if not rows:
        raise ValueError(
            f"no row to stage for {dataset}, hand in at least one row with the properties of "
            f"{contract}"
        )
    names = {name for name, _ in declared}
    for at, row in enumerate(rows, start=1):
        odd = sorted(names ^ set(row))
        if odd:
            raise ValueError(
                f"row {at} of {len(rows)} for {dataset} and its contract differ on {odd}, give "
                f"every row exactly the properties of {contract}"
            )
    return declared


def stage_rows(con, table: str, dataset: str, rows: list[dict]):
    """A temp table with the columns of the dataset's contract, holding `rows`, one dict for
    each row.

    Each value lands under the name of its key, whatever the column order of the contract.
    `staging_columns` decides first whether the rows may be staged: a column added to the
    contract and not to a row would otherwise be written as NULL.
    """
    declared = staging_columns(dataset, rows)
    names = [name for name, _ in declared]
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table} ({column_list(declared)})")
    con.executemany(
        f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
        [tuple(r[c] for c in names) for r in rows],
    )


# Append-only datasets whose schema has grown: a file written before a column existed is read
# with NULL in it, rather than breaking the view or being rewritten.
UNION_BY_NAME = {"gold/evidence"}

# Bronze data written before its audit row, by an ingest that failed in between, is not
# committed: the views show only ingest_ids the audit names, spec 3.1.
COMMITTED = {"bronze/recording", "bronze/electrode", "bronze/event"}


def views(con):
    """One view per dataset on disk; a typed empty view for a dataset with a known schema."""
    # The audit view first, the committed Bronze views read it.
    for dataset in sorted(DATASETS, key=lambda d: d != "bronze/ingest_audit"):
        root = data_dir() / dataset
        for aborted in (p for p in root.rglob("*.parquet") if p.stat().st_size == 0):
            print(f"db: removed {aborted}, an empty file left by an aborted write")
            aborted.unlink()
        if any(root.rglob("*.parquet")):
            con.execute(
                f"CREATE OR REPLACE VIEW {view_name(dataset)} AS SELECT * FROM read_parquet("
                f"'{root.as_posix()}/**/*.parquet', hive_partitioning = true, "
                "hive_types_autocast = false"
                + (", union_by_name = true)" if dataset in UNION_BY_NAME else ")")
                + (" WHERE ingest_id IN (SELECT ingest_id FROM bronze_ingest_audit)"
                   if dataset in COMMITTED else "")
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
    # Every ORDER BY in sql/ is explicit, so arrival order is not kept. The value is in
    # pipeline/settings.py.
    con.execute(f"SET preserve_insertion_order = {settings.PRESERVE_INSERTION_ORDER}")
    views(con)
    run_sql(con, SQL / "lineage" / "lid_generated.sql")
    run_sql(con, SQL / "lineage" / "lid_extras.sql")
    return con


def sha256(path: Path) -> str:
    """Hex digest of a file, read in chunks so a large file is never held in memory."""
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def dataset_version(dataset: str) -> str:
    """sha256 of the sorted list of the dataset's Parquet file digests, spec 5.3."""
    files = (data_dir() / dataset).rglob("*.parquet")
    digests = sorted(sha256(p) for p in files)
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
