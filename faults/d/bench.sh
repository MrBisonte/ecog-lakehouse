#!/usr/bin/env bash
# Fault D, spec 6: a synchronous one-file-at-a-time download loop against one httpfs statement
# over the same files. Wall clock and row count for both. Appends to docs/bench.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
source faults/lib.sh
need_cli "fault d"
[ -f docs/data/manifest.json ] || { echo "fault d: no docs/data/manifest.json, run make publish, skipped"; exit 0; }
serve_docs_data

FAULT_FILES=$("$PY" -c "
import json, sys
files = [f['path'] for f in json.load(open('docs/data/manifest.json'))['files'] if f['path'].endswith('.parquet')]
print('[' + ', '.join(repr('$BASE_URL/' + f) for f in files) + ']')")
export FAULT_FILES
n_files=$("$PY" -c "import json; print(sum(f['path'].endswith('.parquet') for f in json.load(open('docs/data/manifest.json'))['files']))")

t_plant=$(seconds "$PY" faults/d/plant.py "$BASE_URL")
rows_plant=$("$PY" faults/d/plant.py "$BASE_URL")
t_fix=$(seconds "$DUCKDB" -c "$(cat faults/d/fix.sql)")
rows_fix=$("$DUCKDB" -csv -noheader -c "$(cat faults/d/fix.sql)")

{
  echo
  echo "## Fault D: synchronous one-file-at-a-time loop"
  echo
  echo "$n_files Parquet files from \`docs/data/manifest.json\` over \`$BASE_URL\`. Before: \`faults/d/plant.py\`, urllib, one file after another into a temp directory, then count. After: \`faults/d/fix.sql\`, one \`read_parquet\` over the URL list. Seconds are wall clock of one run each."
  echo
  echo "| approach | rows | seconds |"
  echo "|---|---|---|"
  echo "| before, sequential download then count | $rows_plant | $t_plant |"
  echo "| after, one httpfs statement | $rows_fix | $t_fix |"
} | tee -a "$BENCH_MD"
