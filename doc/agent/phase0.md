# Agent prompt, phase 0

Paste as the first message in Claude Code inside `<checkout>`. This is the version that was actually used; it supersedes the earlier draft.

Amendment of 2026-09-20, after the `lid` layout moved to arch-standards: step 3 below means use the generated macros in `sql/lineage/lid_generated.sql` (copied by `make lineage`, never edited) for encode, decode and validate, and hand write only the navigation, `lid_trace`, `lid_children` and `lid_parent`, plus the tables, text form and UUID bridge they need, in `sql/lineage/lid_extras.sql`. Spec sections 12.5 (canary records) and 3.3 (`gold/dataset_manifest`) are in scope as well.

```
You are building phase 0 of the repository ecog-lakehouse at <checkout>
(Windows path <checkout>, a Windows drive mounted in WSL2). A zip named
ecog-lakehouse.zip is in or next to that folder; it contains the repository with its
.git history.

Pre-flight, do this first and report the result of each line before
anything else:

1. If <checkout> has no .git directory, unzip ecog-lakehouse.zip so that the
   repository root is <checkout> itself, not <checkout>/ecog-lakehouse.
   Then `git log --oneline`: expect exactly one commit, "chore: scaffold
   ecog-lakehouse with intent, spec, plan, ADRs and phase 0 agent prompt".
   `git status --short` must be empty. If either is not true, stop and show me.
2. `python3 --version` must be 3.12 or newer. Create a venv inside WSL, not on
   the Windows mount: `python3 -m venv <venv> && source
   <venv>/bin/activate && pip install -e ".[dev]"`.
3. `export DATA_DIR=$HOME/data/ecog-lakehouse && mkdir -p $DATA_DIR`. All data and
   DuckDB working files live there: raw/, bronze/, silver/, gold/,
   keyring.duckdb. Only docs/data/ stays inside the repo. Never write anything
   but source, docs and docs/data/ inside the repo root; if a script wants to
   write elsewhere in the repo, that is a bug.
4. `make lint` is expected to fail right now because ruff has no .py file to
   check yet. It must pass from step 1 of the build onward.

Then read, in this order and in full: CLAUDE.md, doc/intent.md, doc/spec.md,
doc/plan.md, doc/REVIEW.md, every file under adr/.
doc/spec.md is the contract. If you find a contradiction
between doc/spec.md and anything else, stop and tell me which line; do not
resolve it yourself. doc/agent/phase0.md is an earlier copy of this prompt;
this message supersedes it, update that file to match before your first
commit.

Goal of phase 0: `make all SYNTH=1` and `make test` pass from a clean clone
with no network access, on synthetic data with the exact Bronze schema in
doc/spec.md section 3.1. No real data, no faults, no site in this phase.

Use plan mode first. Produce the plan as a numbered list following "Order
inside phase 0" in doc/plan.md, with the files you will create for each step.
Wait for my approval before writing code.

Build, in this order:

1. pipeline/synth.py. Three subjects, two experiments (fingerflex, motor_basic),
   64 channels, 60 s at 1 kHz, events every 2 s, one NaN burst per subject.
   Output must look like what convert_mat.py will produce from real files:
   write it through the same adapter interface, not as a shortcut.
2. pipeline/convert_mat.py with an adapter registry. Phase 0 has only the
   synthetic adapter. An unknown experiment is skipped with a logged reason.
   Every converted file writes one bronze/ingest_audit row with sha256, bytes,
   sample_rate_hz, rows_written, tool, tool_version (git commit), duckdb_version,
   ingested_at (UTC). Assign ingest_ord as the rank of sha256. Set lid on every
   Bronze row per spec section 12 with layer 1.
3. sql/lineage.sql: the macros in spec 12.3, including lid_parent. Test them
   first: encode then decode must round-trip for every field; lid_text must be
   26 Crockford base32 characters; lid_parse(lid_text(x)) = x; lid_children(ing)
   must return exactly the records of that ingest_ord; lid_trace on a Bronze row
   must return source_path, source_url and sha256 from ingest_audit.
4. sql/bronze, sql/silver, sql/gold as plain DuckDB SQL files with {{var}}
   placeholders; pipeline/run.py renders and executes them in order. No ORM.
   Silver pseudonymises through keyring.duckdb (HMAC-SHA256, secret generated
   on first run, never committed) and writes access_log on any re-identification.
   Silver recording sorted by lid, sample_idx, row group 200000. Gold per spec
   3.3; line_noise_ratio in Python, NULL when the excerpt is under 10 s.
5. contracts/*.yaml, one per Silver and Gold dataset, Open Data Contract
   Standard v3. A test asserts each contract's columns and types match the
   Parquet schema actually written.
6. governance/requirements.csv with at least these rows, then
   pipeline/checks.py that generates one check per row, runs it, appends to
   gold/evidence with dataset_version = sha256 of the sorted file digests:
     Part11-11.10e   hash_match           bronze/ingest_audit
     Part11-11.10e   not_null lid         silver/recording
     GDPR-Art9       no_direct_identifier silver/recording  subject_src
     GDPR-Art9       no_direct_identifier gold/*            subject_src
     ALCOA+-Original hash_match           bronze/ingest_audit
     ALCOA+-Complete row_count_min        silver/recording
     ISO13485-4.2.5  unique lid           silver/record
     ISO13485-4.2.5  partition_layout     silver/recording  max 200000, min 2
   All eight check kinds in spec 5.2 must be implemented even if only some are
   used, each with a unit test.
7. tests/: contracts match SQL output; evidence is append-only across two runs
   and dataset_version is identical for identical inputs; no_direct_identifier
   fails when subject_src is deliberately leaked into Silver; a malformed
   generated SQL is rejected by the generator; the lineage tests from step 3.
8. Update doc/REVIEW.md phase 0 entry: what you checked, what failed, what
   changed. Update doc/spec.md only if the code forced a change, and say so in
   doc/REVIEW.md. A decision that changes an ADR gets a new ADR (next number
   ADR-0005) that supersedes it; accepted ADRs are not edited.

Rules that override your defaults:
- Shortest thing that works. Standard library before a dependency. The only
  runtime dependencies are duckdb, scipy, pyyaml. Ask before adding one. No
  h5py and no ulid package: the ULID text form is 26 characters of Crockford
  base32 over 128 bits and fits in a 15-line function.
- Every number that ends up anywhere is a query result.
- Never write to Bronze partitions that exist. Never put subject_src outside
  Bronze and keyring.duckdb.
- Commas, never dashes, in every file you write. Conventional Commits, one
  commit per step above.
- .gitignore is an allow list. If a new file type is needed, add one allow
  line and say so. Before every commit run `git status --short` and confirm
  nothing under data/, docs/data/ or any .duckdb, .parquet, .mat appears.
- Run `make lint` and `make test` before every commit. Do not commit red.
- The repo is on a Windows mount: keep the number of files small, do not
  generate per-row or per-partition files inside the repo, and expect git and
  pytest collection to be slower than native.
- When done, run a verifier pass: clone the repo to a temp dir inside WSL
  (not on /mnt/c), run `make all SYNTH=1` and `make test` there with a fresh
  DATA_DIR, paste the output into doc/REVIEW.md.

Report back with: the pre-flight results, the commit list, the test count,
the doc/REVIEW.md entry, and any place where you had to guess. Guesses are
fine if they are listed.
```
