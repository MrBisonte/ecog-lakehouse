"""docs/bench.md: the machine it ran on, and what the current DATA_DIR holds, per experiment.

Every number is a query result or read from the system at run time.
Bronze counts leave the canary subjects out, so the table describes the source library.
Build wall clock is the span from the first ingestion of the audit to the last evidence
row, so it assumes one build per DATA_DIR and leaves fetch and publish out.
"""

import datetime
import os
import platform
import subprocess
import sys
from pathlib import Path

import duckdb

from pipeline import convert_mat, db

OUT = db.REPO / "docs" / "bench.md"
# Same default as faults/lib.sh, which the fault benches run.
DUCKDB_CLI = Path(os.environ.get("DUCKDB", Path.home() / ".local" / "duckdb-alpha" / "duckdb"))

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


def fmt_int(n: int) -> str:
    """15336887 as `15,336,887`."""
    return f"{n:,}"


def fmt_mib(n_bytes: int) -> str:
    """Bytes as MiB, two decimals, thousands separated: 1360689759 as `1,297.65 MiB`."""
    return f"{n_bytes / 2**20:,.2f} MiB"


def fmt_seconds(seconds: float) -> str:
    """Seconds, two decimals."""
    return f"{seconds:,.2f}"


def cell(column: str, value) -> str:
    """One table cell: NULL, MiB for a `*_bytes` column, seconds for a duration, separators for integers."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int) and column.endswith("_bytes"):
        return fmt_mib(value)
    if isinstance(value, int):
        return fmt_int(value)
    if isinstance(value, float):
        return fmt_seconds(value)
    if isinstance(value, datetime.timedelta):
        return fmt_seconds(value.total_seconds())
    return str(value)


def mem_total_bytes(meminfo: str) -> int | None:
    """MemTotal of a /proc/meminfo text in bytes, None when the line is missing."""
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    return None


def network_location(environ) -> str:
    """Where the fault benches read from: BASE_URL, or loopback, faults/serve.py, when unset."""
    return environ.get("BASE_URL") or "loopback"


def cli_version(path: Path) -> str:
    """`duckdb --version` of the CLI the fault benches run, `not installed` when absent."""
    if not os.access(path, os.X_OK):
        return "not installed"
    return subprocess.run([str(path), "--version"], capture_output=True, text=True, check=False).stdout.strip()


def setup_rows() -> list[tuple[str, str]]:
    """(setting, value) of the machine and software this run used, read at run time."""
    meminfo = Path("/proc/meminfo")
    ram = mem_total_bytes(meminfo.read_text()) if meminfo.exists() else None
    return [
        ("CPU count", cell("cpus", os.cpu_count())),
        ("RAM", "unknown" if ram is None else fmt_mib(ram)),
        ("Python", platform.python_version()),
        ("DuckDB Python", duckdb.__version__),
        ("DuckDB CLI", cli_version(DUCKDB_CLI)),
        ("git commit", db.git_commit()),
        ("Network location", network_location(os.environ)),
    ]


def table(columns: list[str], rows) -> str:
    """A Markdown table, every cell through cell()."""
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        lines.append("| " + " | ".join(cell(c, v) for c, v in zip(columns, row)) + " |")
    return "\n".join(lines)


def markdown(cur) -> str:
    """The result of a DuckDB cursor as a Markdown table."""
    return table([d[0] for d in cur.description], cur.fetchall())


def build_files():
    """(layer, experiment, bytes) per recording Parquet file, from the file system."""
    rows = []
    for layer in ("bronze", "silver"):
        for path in (db.data_dir() / layer / "recording").rglob("*.parquet"):
            experiment = next(p.split("=", 1)[1] for p in path.parts if p.startswith("experiment="))
            rows.append((layer, experiment, path.stat().st_size))
    return rows


def main(argv=None) -> int:
    con = db.connect()
    con.execute("CREATE TEMP TABLE build_files (layer VARCHAR, experiment VARCHAR, bytes BIGINT)")
    con.executemany("INSERT INTO build_files VALUES (?, ?, ?)", build_files() or [(None, None, None)])
    con.execute("CREATE TEMP TABLE canary (subject_src VARCHAR)")
    con.executemany("INSERT INTO canary VALUES (?)", [(s,) for s in convert_mat.CANARY_SUBJECTS])
    commit, duckdb_version, files, wall_clock = con.execute(BUILD).fetchone()
    text = "\n".join([
        "# Benchmarks",
        "",
        "## Setup",
        "",
        "Read by `pipeline/bench_doc.py` when this file was written.",
        "",
        table(["setting", "value"], setup_rows()),
        "",
        "## Build",
        "",
        (
            f"Counts of the build in `DATA_DIR`, built at commit `{commit}` with DuckDB "
            f"{duckdb_version}. Canary subjects are left out. Bytes are the recording Parquet "
            "files of each layer."
        ),
        "",
        markdown(con.execute(TABLE)),
        "",
        (
            f"Files ingested: {cell('files', files)}. Build wall clock, first ingestion to last "
            f"evidence row: {cell('wall_clock', wall_clock)} seconds."
        ),
        "",
    ])
    OUT.write_text(text, encoding="utf-8")
    print(f"bench_doc: wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
