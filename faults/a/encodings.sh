#!/usr/bin/env bash
# Issue 29: ts_ms and sample_idx lose their dictionary in sorted row groups. Measures, changes
# nothing in the pipeline. Part one: the encodings of every silver/recording file, per column,
# from the Parquet metadata. Part two: the Fault A partition written under ENCODINGS_DIR as
# Parquet version 1 or 2, snappy or zstd, with the sort order and row group size of fix.sql;
# each variant read by DuckDB 1.5.5 and the CLI, then queried over loopback as bench.sh does.
# Variant files that exist are reused unless ENCODINGS_REBUILD=1. Replaces its section of
# BENCH_MD. The SQL is in faults/a/encodings.py.
set -euo pipefail
cd "$(dirname "$0")/../.."
source faults/lib.sh
need_cli "fault a encodings"; need_silver "fault a encodings"
pick_partition

sql() { "$PY" faults/a/encodings.py "$@"; }
# py <sql>: the first column of every row, one per line, from DuckDB 1.5.5, the pipeline's engine.
py() { "$PY" -c 'import duckdb, sys; [print(r[0]) for r in duckdb.execute(sys.argv[1]).fetchall()]' "$1"; }
cli() { "$DUCKDB" -list -noheader -c "$1"; }

DIR=${ENCODINGS_DIR:-$DATA_DIR/scratch/encodings}
PORT=${ENCODINGS_PORT:-8765}
SILVER="$DATA_DIR/silver/recording/*/*/*.parquet"
PARTITION="$DATA_DIR/silver/recording/experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT/*.parquet"
VARIANTS="v1_snappy v2_snappy v1_zstd v2_zstd"  # <parquet version>_<compression>
REF=$DIR/v1_snappy.parquet                      # today's encoding

mkdir -p "$DIR"
for v in $VARIANTS; do
  f=$DIR/$v.parquet
  if [ ! -s "$f" ] || [ "${ENCODINGS_REBUILD:-0}" = 1 ]; then
    # Written aside and moved, so an aborted write never leaves a file the next run reuses.
    py "SET temp_directory = '$DIR/.tmp'; $(sql write "$PARTITION" "$f.part" "${v%_*}" "${v#*_}")" >/dev/null
    mv "$f.part" "$f"
  fi
done

# Same as faults/a/bench.sh, a test holds them equal.
SETUP="SET unsafe_disable_etag_checks = true;"
AGGREGATE="SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1"
RECORDS=$("$DUCKDB" -csv -noheader -c "SELECT count(DISTINCT lid) FROM read_parquet('$REF')")
LID=$("$DUCKDB" -csv -noheader -c "SELECT DISTINCT lid FROM read_parquet('$REF') ORDER BY lid LIMIT 1 OFFSET $((RECORDS / 2))")
ONE_RECORD="SELECT avg(value_uv), count(*) FROM read_parquet([URLS]) WHERE lid = '$LID'"

# http() <sql>: "GET requests | MiB received" of one run, from EXPLAIN ANALYZE's HTTP stats.
http() {
  local out
  out=$("$DUCKDB" -c "$SETUP EXPLAIN ANALYZE $1" 2>&1)
  echo "$(echo "$out" | grep -o -E '#GET: [0-9]+' | grep -o -E '[0-9]+') | $(echo "$out" | grep -o -E 'in: [0-9.]+ [A-Za-z]+' | cut -d' ' -f2-)"
}

"$PY" faults/serve.py "$DIR" "$PORT" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT
URL=http://127.0.0.1:$PORT
sleep 1

READ=$(py "$(sql read "$REF")")
# same <reader output>: "same" when it matches v1 snappy read by DuckDB 1.5.5, else what it said.
same() { if [ "$1" = "$READ" ]; then echo same; else echo "differs: ${1##*$'\n'}"; fi; }

disk_row() {
  local f=$DIR/$1.parquet
  echo "| ${1/_/ } | $(thousands "$(wc -c < "$f")") | $(py "$(sql cells "$f")") | $(same "$(py "$(sql read "$f")" 2>&1 || true)") | $(same "$(cli "$(sql read "$f")" 2>&1 || true)") |"
}

http_row() {
  local urls="'$URL/$1.parquet'" agg one
  agg=${AGGREGATE/URLS/$urls}
  one=${ONE_RECORD/URLS/$urls}
  echo "| ${1/_/ } | $(http "$agg") | $(spread3 "$DUCKDB" -c "$SETUP $agg") | $(http "$one") | $(spread3 "$DUCKDB" -c "$SETUP $one") |"
}

section() {
  echo "Issue 29, measured by \`faults/a/encodings.sh\`. DuckDB Python $(py "SELECT version()"), the pipeline's engine, reads the Parquet metadata and writes the variants; the CLI \`$("$DUCKDB" --version)\` reads them too and runs the queries over HTTP."
  echo
  echo "\`silver/recording\` in DATA_DIR as the pipeline wrote it, $(py "$(sql files "$SILVER")"), from parquet_metadata. A row group keeps a dictionary when its column chunk has a dictionary page."
  echo
  echo "| column | encodings | row groups with a dictionary | compressed bytes | uncompressed bytes | compressed bytes per value | share of compressed bytes, percent |"
  echo "|---|---|---|---|---|---|---|"
  py "$(sql columns "$SILVER")"
  echo
  echo "Subject partition \`experiment=$FAULT_EXPERIMENT/subject_pid=$FAULT_SUBJECT\`, the smallest non canary one, $(py "$(sql files "$PARTITION")") in Silver, written once per variant into one file under ENCODINGS_DIR by \`$(py "$(sql writer "$DIR/*.parquet")")\`, sorted by lid, sample_idx, row groups of 198,656 rows, the columns of \`faults/a/fix.sql\`'s output. Variant names are Parquet writer version and compression; v1 snappy is today's. \`same\` means the row count and sum match v1 snappy read by DuckDB Python, $READ."
  echo
  echo "| variant | file bytes | row groups | ts_ms bytes | sample_idx bytes | value_uv bytes | ts_ms encodings | sample_idx encodings | value_uv encodings | DuckDB Python read | CLI read |"
  echo "|---|---|---|---|---|---|---|---|---|---|---|"
  for v in $VARIANTS; do disk_row "$v"; done
  echo
  echo "The same files over \`$URL\`, \`faults/serve.py\` on loopback, with the CLI. Aggregate: \`$AGGREGATE\`. One record: \`$ONE_RECORD\`, the middle record of $(thousands "$RECORDS"). Seconds are min / median / max of three CLI runs each; GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE."
  echo
  echo "| variant | aggregate GETs | aggregate received | aggregate, s min / median / max | one record GETs | one record received | one record, s min / median / max |"
  echo "|---|---|---|---|---|---|---|"
  for v in $VARIANTS; do http_row "$v"; done
}
write_section "## Fault A encodings: delta and zstd against the lost dictionary" section
