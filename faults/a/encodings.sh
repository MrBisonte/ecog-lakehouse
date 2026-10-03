#!/usr/bin/env bash
# Issue 29: ts_ms and sample_idx lose their dictionary in sorted row groups. Measures, changes
# nothing in the pipeline. The encodings of every silver/recording file, per column, from the
# Parquet metadata. Replaces its section of BENCH_MD. The SQL is in faults/a/encodings.py.
set -euo pipefail
cd "$(dirname "$0")/../.."
md=${BENCH_MD:-docs/bench.md}
source faults/lib.sh
BENCH_MD=$md  # lib.sh pins docs/bench.md; a trial run points elsewhere
need_cli "fault a encodings"; need_silver "fault a encodings"

sql() { "$PY" faults/a/encodings.py "$@"; }
# py <sql>: the first column of every row, one per line, from DuckDB 1.5.5, the pipeline's engine.
py() { "$PY" -c 'import duckdb, sys; [print(r[0]) for r in duckdb.execute(sys.argv[1]).fetchall()]' "$1"; }

SILVER="$DATA_DIR/silver/recording/*/*/*.parquet"
{
  echo "\`silver/recording\` in DATA_DIR as the pipeline wrote it, $(py "$(sql files "$SILVER")"), read with DuckDB $(py "SELECT version()") from parquet_metadata. A row group keeps a dictionary when its column chunk has a dictionary page."
  echo
  echo "| column | encodings | row groups with a dictionary | compressed bytes | uncompressed bytes | compressed bytes per value | share of compressed bytes, percent |"
  echo "|---|---|---|---|---|---|---|"
  py "$(sql columns "$SILVER")"
} | replace_section "## Fault A encodings: delta and zstd against the lost dictionary"
