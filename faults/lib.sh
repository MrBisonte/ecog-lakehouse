#!/usr/bin/env bash
# Shared by every faults/*/bench.sh: the DuckDB CLI, DATA_DIR, a BASE_URL that serves docs/data
# over HTTP (GitHub Pages when set, a local python http.server otherwise), a timer and the
# smallest non canary Silver partition. Source it from the repo root.
export DATA_DIR=${DATA_DIR:-$HOME/data/ecog-lakehouse}
DUCKDB=${DUCKDB:-$HOME/.local/duckdb-alpha/duckdb}
PY=${PY:-python3}
BENCH_MD=docs/bench.md

need_cli() {
  [ -x "$DUCKDB" ] || { echo "$1: no DuckDB CLI at $DUCKDB, skipped (DUCKDB=<path> to point at one)"; exit 0; }
}

need_silver() {
  ls "$DATA_DIR"/silver/recording/*/*/*.parquet >/dev/null 2>&1 || { echo "$1: no Silver under $DATA_DIR, skipped"; exit 0; }
}

# BASE_URL serves docs/data. Without one, faults/serve.py on 127.0.0.1:8765 for this run only:
# it honours Range requests, the stock http.server does not and DuckDB then downloads whole files.
serve_docs_data() {
  if [ -z "${BASE_URL:-}" ]; then
    "$PY" faults/serve.py docs/data 8765 >/dev/null 2>&1 &
    SERVER_PID=$!
    trap 'kill $SERVER_PID 2>/dev/null' EXIT
    BASE_URL=http://127.0.0.1:8765
    sleep 1
  fi
  export BASE_URL
}

# seconds() <command...>: wall clock of the command, three decimals, output discarded.
seconds() {
  local t0 t1
  t0=$(date +%s.%N)
  "$@" >/dev/null 2>&1
  t1=$(date +%s.%N)
  printf '%.3f' "$(echo "$t1 - $t0" | bc)"
}

# spread3() <command...>: "min / median / max" of three seconds() runs, two decimals each.
# Single runs vary, so the spread is shown beside the median.
spread3() {
  local runs
  runs=$({ seconds "$@"; echo; seconds "$@"; echo; seconds "$@"; echo; } | sort -n)
  # shellcheck disable=SC2086  # three sorted numbers, split on purpose
  printf '%.2f / %.2f / %.2f' $runs
}

# The smallest non canary partition of silver/recording, as FAULT_EXPERIMENT FAULT_SUBJECT.
pick_partition() {
  read -r FAULT_EXPERIMENT FAULT_SUBJECT < <("$PY" - <<'EOF'
from pipeline import db
con = db.connect()
print(*con.execute("""
    SELECT experiment, subject_pid FROM silver_recording
    WHERE lid IN (SELECT lid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 0)
    GROUP BY ALL ORDER BY count(*) LIMIT 1""").fetchone())
EOF
)
  export FAULT_EXPERIMENT FAULT_SUBJECT
}
