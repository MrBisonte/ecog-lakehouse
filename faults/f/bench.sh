#!/usr/bin/env bash
# Fault F, spec 6: flaky remote reads without retries against retries with backoff. A proxy in
# front of BASE_URL answers 503 to one range request in ten. Ten attempts per setting: success
# rate and mean wall clock. The attempts run on the pipeline's DuckDB (Python), which honours
# http_retries = 0; the 2.0 alpha CLI retries a 503 on its own and is reported as a third row.
# Appends to docs/bench.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
source faults/lib.sh
need_cli "fault f"
FILE=$(ls docs/data/faults/a/good/*/*/data_0.parquet 2>/dev/null | head -1) || true
[ -n "$FILE" ] || { echo "fault f: no docs/data/faults/a/good, run faults/a/bench.sh first, skipped"; exit 0; }
serve_docs_data
FRACTION=${FRACTION:-0.1}
"$PY" faults/f/flaky_proxy.py "$BASE_URL" 8766 "$FRACTION" &
PROXY_PID=$!
trap 'kill $PROXY_PID ${SERVER_PID:-} 2>/dev/null' EXIT
sleep 1
export FAULT_URL="http://127.0.0.1:8766/${FILE#docs/data/}"
BEFORE="SET http_retries = 0; SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet(getenv('FAULT_URL')) GROUP BY 1;"
AFTER=$(cat faults/f/fix.sql)

# Ten attempts of one statement list on the pipeline's DuckDB: "successes/10 mean_seconds".
python_attempts() {  # getenv() exists in the CLI only; the URL is spliced in as a literal
  "$PY" - "$1" "$FAULT_URL" <<'EOF'
import sys, time, duckdb
sql = sys.argv[1].replace("getenv('FAULT_URL')", repr(sys.argv[2]))
ok, total = 0, 0.0
for _ in range(10):
    con = duckdb.connect()
    t0 = time.perf_counter()
    try:
        con.execute(sql).fetchone()
        ok += 1
    except duckdb.Error:
        pass
    total += time.perf_counter() - t0
print(f"{ok}/10 {total / 10:.3f}")
EOF
}

cli_attempts() {  # the same ten attempts on the CLI
  local ok=0 total=0 t0 t1
  for _ in $(seq 1 10); do
    t0=$(date +%s.%N)
    if "$DUCKDB" -c "$1" >/dev/null 2>&1; then ok=$((ok + 1)); fi
    t1=$(date +%s.%N)
    total=$(echo "$total + $t1 - $t0" | bc)
  done
  echo "$ok/10 $(printf '%.3f' "$(echo "$total / 10" | bc -l)")"
}

py_version=$("$PY" -c "import duckdb; print(duckdb.__version__)")
before=$(python_attempts "$BEFORE")
after=$(python_attempts "$AFTER")
alpha=$(cli_attempts "$BEFORE")

{
  echo
  echo "## Fault F: flaky remote reads without retries"
  echo
  echo "\`faults/f/flaky_proxy.py\` in front of \`$BASE_URL\`, 503 on a fraction $FRACTION of range requests, deterministic. Query: the Fault A aggregate, one range request per row group, over \`${FILE#docs/data/}\`. Ten attempts per row, each timed. The first two rows run on DuckDB $py_version, the pipeline's engine; the third on the CLI \`$("$DUCKDB" --version)\`, which retries a 503 on its own whatever http_retries says."
  echo
  echo "| engine, setting | successes | mean seconds |"
  echo "|---|---|---|"
  echo "| before, $py_version, http_retries = 0 | ${before% *} | ${before#* } |"
  echo "| after, $py_version, http_retries = 8, wait 50 ms, backoff 2 | ${after% *} | ${after#* } |"
  echo "| 2.0 alpha CLI, http_retries = 0 | ${alpha% *} | ${alpha#* } |"
} | tee -a "$BENCH_MD"
