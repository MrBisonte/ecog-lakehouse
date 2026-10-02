#!/usr/bin/env bash
# Fault D, spec 6: a synchronous one-file-at-a-time download loop against one httpfs statement
# over the same files. Wall clock and row count for both. Replaces its section of docs/bench.md.
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
export FAULT_MANIFEST="$BASE_URL/manifest.json"
export FAULT_BASE="$BASE_URL"
n_files=$("$PY" -c "import json; print(sum(f['path'].endswith('.parquet') for f in json.load(open('docs/data/manifest.json'))['files']))")

t_plant=$(seconds "$PY" faults/d/plant.py "$BASE_URL")
rows_plant=$("$PY" faults/d/plant.py "$BASE_URL")
t_fix=$(seconds "$DUCKDB" -c "$(cat faults/d/fix.sql)")
rows_fix=$("$DUCKDB" -csv -noheader -c "$(cat faults/d/fix.sql)")
t_verify=$(seconds "$DUCKDB" -c "$(cat faults/d/verify.sql)")
verified=$("$DUCKDB" -csv -noheader -c "$(cat faults/d/verify.sql)")
files_fix=${verified%,*}; mismatches=${verified#*,}

{
  echo "$n_files Parquet files from \`docs/data/manifest.json\` over \`$BASE_URL\`. Before: \`faults/d/plant.py\`, urllib, one file after another into a temp directory, then count. After: \`faults/d/fix.sql\`, one \`read_parquet\` over the URL list, then \`faults/d/verify.sql\`, every file read once more in full with read_blob and its sha256 compared with the manifest, the integrity check that replaces the CDN's ETag. Seconds are wall clock of one run each; the digest check downloads every byte, so it is timed apart."
  echo
  echo "| approach | rows | seconds | digest check seconds | files hashed | digest mismatches |"
  echo "|---|---|---|---|---|---|"
  echo "| before, sequential download then count | $(thousands "$rows_plant") | $t_plant | | 0 | not checked |"
  echo "| after, one httpfs statement, then verify.sql | $(thousands "$rows_fix") | $t_fix | $t_verify | $files_fix | $mismatches |"
} | replace_section "## Fault D: synchronous one-file-at-a-time loop"
