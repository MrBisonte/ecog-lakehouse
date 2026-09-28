# CLAUDE.md

Governed lakehouse over public ECoG recordings with four planted performance faults. Read `doc/intent.md`, `doc/spec.md`, `doc/plan.md` before changing anything. `doc/spec.md` is the contract; if code and spec disagree, fix one and say which.

## Stack
Python 3.12, DuckDB, Parquet, `make`. Plain SQL in `sql/`, no ORM. DuckDB-WASM in `docs/index.html`. No other runtime dependency without an ADR.

## Rules
- Every number shown anywhere is a query result. Nothing typed by hand.
- Bronze is append-only. Never rewrite a Bronze partition.
- `subject_src` never appears outside Bronze and `keyring.duckdb`. A test enforces it.
- All data and DuckDB working files live in `DATA_DIR` (default `$HOME/data/ecog-lakehouse`), outside the repo: `data/raw`, `data/bronze`, `data/silver`, `data/gold`, `keyring.duckdb`. The repo is on a Windows mount (`/mnt/c/Prj/ecog-lakehouse`); writing data inside it is a bug. `docs/data/` is the only published data and the only data inside the repo.
- `.gitignore` is an allow list: only code, SQL, contracts, governance CSVs, docs and the site are tracked. A new file type needs a new allow line.
- Published file under 95 MB, `docs/data/` under 500 MB. `make publish` enforces.
- No third-party request at view time except the pinned DuckDB-WASM CDN. System font stack.
- Commas, never dashes. Conventional Commits.
- Ponytail: shortest thing that works. Standard library before a dependency. Delete before adding.

## Commands
`make all SYNTH=1` synthetic end to end. `make all` real data. `make checks` governance only. `make bench` faults. `make test`.

## Hooks
Pre-commit: `ruff`, `python scripts/lint_doc.py` on every `.md`, `make test`. A failing hook blocks the commit.

## Review
Every phase ends with a pass recorded in `doc/REVIEW.md`: what was checked, what failed, what changed. A verifier subagent reruns `make all SYNTH=1` and `make test` from a clean clone before a phase is marked done.

## Identifiers
Follow arch-standards/data/ids/SPEC.md. `lid` is generated from its layout file; `sql/lineage/` holds the generated macros plus the hand written `lid_trace`, `lid_children`, `lid_parent`.

## Faults
`faults/<a|d|f|g>/` each hold `plant.*`, `fix.*`, `bench.sh`. Do not "fix" a planted fault in the pipeline itself; the pipeline is already the fixed version.
