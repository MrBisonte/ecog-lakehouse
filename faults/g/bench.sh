#!/usr/bin/env bash
# Fault G, spec 6: pathological generated SQL. Parse plus bind time of the 512 level nested OR
# against the IN list, and the parser's message for the malformed variant. Appends to
# docs/bench.md. silver_record is read from DATA_DIR so the bind has real columns.
set -euo pipefail
cd "$(dirname "$0")/../.."
source faults/lib.sh
need_cli "fault g"; need_silver "fault g"
OUT=docs/data/faults/g
"$PY" faults/g/plant.py "$OUT"
VIEW="CREATE VIEW silver_record AS SELECT * FROM read_parquet('$DATA_DIR/silver/record/*.parquet');"

bind_seconds() {  # parse and bind only: EXPLAIN never reads a row
  seconds "$DUCKDB" -c "$VIEW EXPLAIN $(cat "$1")"
}

t_nested=$(bind_seconds "$OUT/nested.sql")
t_fixed=$(bind_seconds "$OUT/fixed.sql")
error=$("$DUCKDB" -c "$VIEW $(cat "$OUT/malformed.sql")" 2>&1 | grep -v '^$' | head -3 | sed 's/^/    /' || true)
depth=$(grep -o '(' "$OUT/nested.sql" | wc -l)

{
  echo
  echo "## Fault G: pathological generated SQL"
  echo
  echo "\`faults/g/plant.py\` wrote three predicates over 512 channels under \`docs/data/faults/g\`. Seconds are wall clock of \`EXPLAIN\` in the CLI, parse and bind, no rows read. The generator in \`pipeline/checks.py\` emits the IN form and refuses the other two (test \`test_generator_rejects_malformed_and_deeply_nested_sql\`)."
  echo
  echo "| predicate | nesting | EXPLAIN seconds |"
  echo "|---|---|---|"
  echo "| before, one OR per channel, nested | $depth | $t_nested |"
  echo "| after, channel_idx IN (...) | 1 | $t_fixed |"
  echo
  echo "Malformed variant, one parenthesis short, as the parser reports it:"
  echo
  echo '```'
  echo "$error"
  echo '```'
} | tee -a "$BENCH_MD"
