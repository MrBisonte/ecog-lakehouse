#!/usr/bin/env bash
# Fault A sweep, issue #28: the subject partition of bench.sh, sorted by lid, sample_idx, written as
# one file per row group size and served on loopback. The aggregate of bench.sh runs over each file
# in the DuckDB CLI and in DuckDB through Python, with the GET requests and bytes received each
# costs, three runs each. The CLI's external file cache settings are extra rows. DUCKDB_BEFORE names
# a second, older CLI to set beside it. Replaces its section of docs/bench.md. Not part of make
# bench; the files stay under SWEEP_DIR, nothing is published.
set -euo pipefail
cd "$(dirname "$0")/../.."
source faults/lib.sh
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
CLIS=("$DUCKDB")
[ -x "${DUCKDB_BEFORE:-}" ] && CLIS=("$DUCKDB_BEFORE" "$DUCKDB")

# block_setting <cli>: the name this build gives the remote block size of its external file cache;
# it was renamed between alpha builds. Empty when the build has neither.
block_setting() {
  "$1" -list -noheader -c "SELECT name FROM duckdb_settings() WHERE name IN ('external_file_cache_remote_block_size', 'external_file_cache_remote_max_block_size') LIMIT 1"
}

# agree <values, one per line>: one value where the three runs agree, all three where they do not.
agree() { uniq | paste -sd, | sed 's/,/, /g'; }

row() {  # rows per row group, engine (a CLI path, or python), setting ("" for the default)
  local f=$SWEEP_DIR/rg_$1.parquet url sql groups label engine runs
  url="'$BASE/rg_$1.parquet'"
  sql=${AGGREGATE/URLS/$url}
  groups=$("$DUCKDB" -csv -noheader -c "SELECT count(DISTINCT row_group_id) FROM parquet_metadata('$f')")
  label=$(thousands "$1"); [ "$groups" = 1 ] && label="one row group"
  if [ "$2" = python ]; then
    engine="$("$PY" -c 'import duckdb; print(duckdb.__version__)'), Python"
    runs=$(for _ in 1 2 3; do "$PY" faults/a/http_stats.py "$sql" || exit 1; done)
  else
    engine="$("$2" --version | cut -d' ' -f1), CLI"
    runs=$(for _ in 1 2 3; do "$2" -c "$3 EXPLAIN ANALYZE $sql" 2>&1 | "$PY" faults/a/http_stats.py - || exit 1; done)
  fi
  echo "| $label | $(thousands "$groups") | $(mib "$(wc -c < "$f")") | $engine | ${3:-default} | $(echo "$runs" | cut -d'|' -f1 | tr -d ' ' | agree) | $(echo "$runs" | cut -d'|' -f2 | sed 's/^ //' | agree) |"
}

section() {
  local n cli block
  echo "DuckDB CLI $(for cli in "${CLIS[@]}"; do printf '`%s`, ' "$("$cli" --version)"; done)and DuckDB \`$("$PY" -c 'import duckdb; print(duckdb.__version__)')\` through Python. Subject partition \`experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT\`, sorted by \`lid, sample_idx\`, written as one file per row group size and served by \`faults/serve.py\` on \`$BASE\`. Query: \`$AGGREGATE\`, over one file. GET requests and bytes received are the HTTP statistics of EXPLAIN ANALYZE, three runs each: one value where the runs agree, all three where they do not. Not timed: loopback seconds say nothing about a network. Written by \`faults/a/sweep.sh\`, not by make bench."
  echo
  echo "| rows per row group | row groups | size | engine | setting | GETs | received |"
  echo "|---|---|---|---|---|---|---|"
  for n in $SIZES; do
    for cli in "${CLIS[@]}"; do
      row "$n" "$cli" ""
      row "$n" "$cli" "SET enable_external_file_cache = false;"
      block=$(block_setting "$cli")
      if [ -n "$block" ]; then row "$n" "$cli" "SET $block = 262144;"; fi
    done
    row "$n" python ""
  done
}
write_section "## Fault A sweep: row group size against requests and bytes" section
