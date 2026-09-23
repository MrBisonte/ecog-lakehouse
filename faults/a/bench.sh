#!/usr/bin/env bash
# Fault A, spec 6: single row group, unpartitioned, unsorted against partitioned, sorted,
# 198,656 row groups. Plants both layouts under docs/data/faults/a, then times the same
# aggregate over HTTP with read_ahead_depth = 0 and with the default. Appends to docs/bench.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
source faults/lib.sh
need_cli "fault a"; need_silver "fault a"
pick_partition

rm -rf docs/data/faults/a
mkdir -p docs/data/faults/a/bad
"$DUCKDB" < faults/a/plant.sql
"$DUCKDB" < faults/a/fix.sql
serve_docs_data

BAD=docs/data/faults/a/bad/recording.parquet
GOOD=docs/data/faults/a/good/experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT/data_0.parquet
QUERY="SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet('URL') GROUP BY 1"

row() {  # name, local path, url
  local groups bytes sorted t_noahead t_default
  groups=$("$DUCKDB" -csv -noheader -c "SELECT count(DISTINCT row_group_id) FROM parquet_metadata('$2')")
  bytes=$(stat -c %s "$2")
  sorted=$("$DUCKDB" -csv -noheader -c "SELECT bool_and(ok) FROM (SELECT (lid, sample_idx) >= lag((lid, sample_idx)) OVER () OR lag(lid) OVER () IS NULL AS ok FROM read_parquet('$2'))")
  t_noahead=$(median3 "$DUCKDB" -c "SET read_ahead_depth = 0; ${QUERY/URL/$3}")
  t_default=$(median3 "$DUCKDB" -c "${QUERY/URL/$3}")
  echo "| $1 | $groups | $bytes | $sorted | $t_noahead | $t_default |"
}

{
  echo
  echo "## Fault A: single row group, unpartitioned, unsorted"
  echo
  echo "DuckDB CLI \`$("$DUCKDB" --version)\`. Subject partition \`experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT\`, the smallest non canary one. Query: \`$QUERY\` over \`$BASE_URL\`. Seconds are the median of three CLI runs each."
  echo
  echo "| layout | row groups | bytes | sorted by lid, sample_idx | read_ahead_depth = 0 | default |"
  echo "|---|---|---|---|---|---|"
  row "before, one row group" "$BAD" "$BASE_URL/faults/a/bad/recording.parquet"
  row "after, partitioned and sorted" "$GOOD" "$BASE_URL/faults/a/good/experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT/data_0.parquet"
} | tee -a "$BENCH_MD"
