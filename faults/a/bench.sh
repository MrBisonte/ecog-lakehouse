#!/usr/bin/env bash
# Fault A, spec 6: single row group, unpartitioned, unsorted against partitioned, sorted,
# 198,656 row groups. Plants both layouts under docs/data/faults/a, then times the same
# aggregate over HTTP with read_ahead_depth = 0 and with the default. Appends to docs/bench.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
source faults/lib.sh
need_cli "fault a"; need_silver "fault a"
pick_partition

# A local run plants both layouts afresh. With BASE_URL set, the published copy is what is
# measured, so the files under docs/data/faults/a stay as committed and describe it.
if [ -z "${BASE_URL:-}" ]; then
  rm -rf docs/data/faults/a
  mkdir -p docs/data/faults/a/bad
  "$DUCKDB" < faults/a/plant.sql
  "$DUCKDB" < faults/a/fix.sql
fi
serve_docs_data

BAD=docs/data/faults/a/bad
GOOD=docs/data/faults/a/good/experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT
# unsafe_disable_etag_checks: GitHub Pages serves one file with different ETags from different
# edges and DuckDB's If-Match then gets a 412; manifest.json carries the digests instead.
QUERY="SET unsafe_disable_etag_checks = true; SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1"

row() {  # name, local directory: every Parquet file in it is one layout, one or more files
  local files urls groups bytes sorted t_noahead t_default
  files=$(ls "$2"/*.parquet)
  urls=$(for f in $files; do printf "'%s', " "$BASE_URL/${f#docs/data/}"; done); urls=${urls%, }
  groups=$("$DUCKDB" -csv -noheader -c "SELECT count(DISTINCT (file_name, row_group_id)) FROM parquet_metadata('$2/*.parquet')")
  bytes=$(cat $files | wc -c)
  sorted=true
  for f in $files; do
    [ "$("$DUCKDB" -csv -noheader -c "SELECT bool_and(ok) FROM (SELECT (lid, sample_idx) >= lag((lid, sample_idx)) OVER () OR lag(lid) OVER () IS NULL AS ok FROM read_parquet('$f'))")" = true ] || sorted=false
  done
  t_noahead=$(median3 "$DUCKDB" -c "SET read_ahead_depth = 0; ${QUERY/URLS/$urls}")
  t_default=$(median3 "$DUCKDB" -c "${QUERY/URLS/$urls}")
  echo "| $1 | $(echo $files | wc -w) | $groups | $bytes | $sorted | $t_noahead | $t_default |"
}

{
  echo
  echo "## Fault A: single row group, unpartitioned, unsorted"
  echo
  echo "DuckDB CLI \`$("$DUCKDB" --version)\`. Subject partition \`experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT\`, the smallest non canary one. Query: \`$QUERY\` over \`$BASE_URL\`, every file of the layout in one read_parquet. Seconds are the median of three CLI runs each."
  echo
  echo "| layout | files | row groups | bytes | sorted by lid, sample_idx | read_ahead_depth = 0 | default |"
  echo "|---|---|---|---|---|---|---|"
  row "before, one row group" "$BAD"
  row "after, partitioned and sorted" "$GOOD"
} | tee -a "$BENCH_MD"
