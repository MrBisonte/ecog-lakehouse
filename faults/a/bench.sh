#!/usr/bin/env bash
# Fault A, spec 6: single row group, unpartitioned, unsorted against partitioned, sorted,
# 198,656 row groups. Plants both layouts under docs/data/faults/a, then times the same
# aggregate over HTTP with read_ahead_depth = 0 and with the default, and the retrieval of one
# record by lid, with the GET requests and bytes each costs. Replaces its section of docs/bench.md.
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
SETUP="SET unsafe_disable_etag_checks = true;"
# Two questions per layout: an aggregate over every row, and the retrieval the layout is for,
# one record by its lid. The record is the middle one of the subject.
AGGREGATE="SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1"
RECORDS=$("$DUCKDB" -csv -noheader -c "SELECT count(DISTINCT lid) FROM read_parquet('$BAD/*.parquet')")
LID=$("$DUCKDB" -csv -noheader -c "SELECT DISTINCT lid FROM read_parquet('$BAD/*.parquet') ORDER BY lid LIMIT 1 OFFSET $((RECORDS / 2))")
ONE_RECORD="SELECT avg(value_uv), count(*) FROM read_parquet([URLS]) WHERE lid = '$LID'"

# http() <sql>: "GET requests | MiB received" of one run, from EXPLAIN ANALYZE's HTTP stats.
http() {
  local out
  out=$("$DUCKDB" -c "$SETUP EXPLAIN ANALYZE $1" 2>&1)
  echo "$(echo "$out" | grep -o -E '#GET: [0-9]+' | grep -o -E '[0-9]+') | $(echo "$out" | grep -o -E 'in: [0-9.]+ [A-Za-z]+' | cut -d' ' -f2-)"
}

row() {  # name, local directory: every Parquet file in it is one layout, one or more files
  local files urls groups bytes sorted agg one
  files=$(ls "$2"/*.parquet)
  urls=$(for f in $files; do printf "'%s', " "$BASE_URL/${f#docs/data/}"; done); urls=${urls%, }
  groups=$("$DUCKDB" -csv -noheader -c "SELECT count(DISTINCT (file_name, row_group_id)) FROM parquet_metadata('$2/*.parquet')")
  bytes=$(cat $files | wc -c)
  sorted=true
  for f in $files; do
    [ "$("$DUCKDB" -csv -noheader -c "SELECT bool_and(ok) FROM (SELECT (lid, sample_idx) >= lag((lid, sample_idx)) OVER () OR lag(lid) OVER () IS NULL AS ok FROM read_parquet('$f'))")" = true ] || sorted=false
  done
  agg=${AGGREGATE/URLS/$urls}
  one=${ONE_RECORD/URLS/$urls}
  echo "| $1 | $(echo $files | wc -w) | $(thousands "$groups") | $(mib "$bytes") | $sorted | $(spread3 "$DUCKDB" -c "$SETUP SET read_ahead_depth = 0; $agg") | $(spread3 "$DUCKDB" -c "$SETUP $agg") | $(http "$agg") | $(spread3 "$DUCKDB" -c "$SETUP $one") | $(http "$one") |"
}

{
  echo "DuckDB CLI \`$("$DUCKDB" --version)\`. Subject partition \`experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT\`, the smallest non canary one, over \`$BASE_URL\`, every file of the layout in one read_parquet. Aggregate: \`$AGGREGATE\`. One record: \`$ONE_RECORD\`, the middle record of $(thousands "$RECORDS"). Seconds are min / median / max of three CLI runs each; GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE."
  echo
  echo "| layout | files | row groups | size | sorted by lid, sample_idx | aggregate, read_ahead_depth = 0, s min / median / max | aggregate, default, s min / median / max | aggregate GETs | aggregate received | one record, s min / median / max | one record GETs | one record received |"
  echo "|---|---|---|---|---|---|---|---|---|---|---|---|"
  row "before, one row group" "$BAD"
  row "after, partitioned and sorted" "$GOOD"
} | replace_section "## Fault A: single row group, unpartitioned, unsorted"
