#!/usr/bin/env bash
# Fault A sweep, issue #28: the subject partition of bench.sh, sorted by lid, sample_idx, written as
# one file per row group size and served on loopback. The aggregate of bench.sh runs over each file
# in the DuckDB CLI and in DuckDB through Python, with the GET requests and bytes received each
# costs. The CLI's external file cache settings are extra rows. Replaces its section of
# docs/bench.md. Not part of make bench; the files stay under SWEEP_DIR, nothing is published.
set -euo pipefail
cd "$(dirname "$0")/../.."
md=${BENCH_MD:-}
source faults/lib.sh
BENCH_MD=${md:-$BENCH_MD}  # lib.sh sets docs/bench.md; a scratch run points BENCH_MD at a copy
need_cli "fault a sweep"; need_silver "fault a sweep"
pick_partition

SWEEP_DIR=${SWEEP_DIR:-$DATA_DIR/scratch/sweep}
SWEEP_PORT=${SWEEP_PORT:-8765}
# Rows per row group: 198,656 is the published layout, 100,000,000 writes one row group.
SIZES="198656 393216 786432 1048576 2097152 4194304 100000000"
SRC="$DATA_DIR/silver/recording/experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT/*.parquet"
mkdir -p "$SWEEP_DIR"
for n in $SIZES; do
  f=$SWEEP_DIR/rg_$n.parquet
  [ -f "$f" ] && [ "${SWEEP_REBUILD:-0}" != 1 ] && continue
  # Written under a temporary name: an aborted COPY must not leave a file the next run reuses.
  "$DUCKDB" -c "COPY (SELECT * FROM read_parquet('$SRC', hive_partitioning = false) ORDER BY lid, sample_idx) TO '$f.tmp' (FORMAT parquet, ROW_GROUP_SIZE $n)"
  mv "$f.tmp" "$f"
done

"$PY" faults/serve.py "$SWEEP_DIR" "$SWEEP_PORT" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT
sleep 1
BASE=http://127.0.0.1:$SWEEP_PORT

AGGREGATE="SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1"
# The CLI's rows: the default, then the two settings of its external file cache, which reads a
# remote file in aligned blocks of external_file_cache_remote_block_size bytes.
CLI_SETTINGS=("" "SET enable_external_file_cache = false;" "SET external_file_cache_remote_block_size = 262144;")

row() {  # rows per row group, engine (cli or python), setting ("" for the default)
  local f=$SWEEP_DIR/rg_$1.parquet url sql groups label stats secs
  url="'$BASE/rg_$1.parquet'"
  sql=${AGGREGATE/URLS/$url}
  groups=$("$DUCKDB" -csv -noheader -c "SELECT count(DISTINCT row_group_id) FROM parquet_metadata('$f')")
  label=$(thousands "$1"); [ "$groups" = 1 ] && label="one row group"
  if [ "$2" = cli ]; then
    stats=$("$DUCKDB" -c "$3 EXPLAIN ANALYZE $sql" 2>&1 | "$PY" faults/a/http_stats.py -)
    secs=$(spread3 "$DUCKDB" -c "$3 $sql")
  else
    stats=$("$PY" faults/a/http_stats.py "$sql")
    secs="not timed"
  fi
  echo "| $label | $(thousands "$groups") | $(mib "$(wc -c < "$f")") | $2 | ${3:-default} | $stats | $secs |"
}

{
  echo "DuckDB CLI \`$("$DUCKDB" --version)\` and DuckDB \`$("$PY" -c 'import duckdb; print(duckdb.__version__)')\` through Python. Subject partition \`experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT\`, sorted by \`lid, sample_idx\`, written as one file per row group size and served by \`faults/serve.py\` on \`$BASE\`. Query: \`$AGGREGATE\`, over one file. GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE. Seconds are min / median / max of three CLI runs on loopback, not evidence of a network. Written by \`faults/a/sweep.sh\`, not by make bench."
  echo
  echo "| rows per row group | row groups | size | engine | setting | GETs | received | s min / median / max |"
  echo "|---|---|---|---|---|---|---|---|"
  for n in $SIZES; do
    for s in "${CLI_SETTINGS[@]}"; do row "$n" cli "$s"; done
    row "$n" python ""
  done
} | replace_section "## Fault A sweep: row group size against requests and bytes"
