# Agent prompt, phase 0

Paste as the first message in Claude Code, Opus model, inside `/mnt/c/Prj/ibrain`.

```
You are building phase 0 of the repository at /mnt/c/Prj/ibrain (Windows path
C:\Prj\ibrain, a Windows drive mounted in WSL2). Read, in this order and in
full before doing anything else: CLAUDE.md, doc/intent.md, doc/spec.md,
doc/plan.md, doc/REVIEW.md, then every file under adr/ and doc/references/.
doc/spec.md is the contract. If you find a contradiction between doc/spec.md
and anything else, stop and tell me which line, do not resolve it yourself.

Before anything else: the repo lives on a Windows mount, so all data and
DuckDB working files must live outside it. DATA_DIR (environment variable,
default $HOME/data/ibrain, already exported by the Makefile) is where
raw/, bronze/, silver/, gold/ and keyring.duckdb go. Only docs/data/ stays
inside the repo. Create DATA_DIR on first run. Never write anything but
source, docs and docs/data/ inside the repo root; if a script wants to write
elsewhere in the repo, that is a bug.

Goal of phase 0: `make all SYNTH=1` and `make test` pass from a clean clone
with no network access, on synthetic data that has the exact Bronze schema in
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
   doc/REVIEW.md. A decision that changes an ADR gets a new ADR that supersedes
   it; accepted ADRs are not edited.

Rules that override your defaults:
- Shortest thing that works. Standard library before a dependency. The only
  runtime dependencies are duckdb, scipy, pyyaml. Ask before adding one. No
  h5py and no ulid package: the ULID text form is 26 characters of Crockford
  base32 over 128 bits and fits in a 15-line function.
- Every number that ends up anywhere is a query result.
- Never write to Bronze partitions that exist. Never put subject_src outside
  Bronze and keyring.duckdb.
- Commas, never dashes, in every file you write. Conventional Commits, one
  commit per step above. .gitignore is an allow list; if a new file type is
  needed, add one allow line and say so.
- Run `make lint` and `make test` before every commit. Do not commit red.
- When done, run a verifier pass: clone the repo to a temp dir, run
  `make all SYNTH=1` and `make test` there, paste the output into doc/REVIEW.md.

Report back with: the commit list, the test count, the doc/REVIEW.md entry,
and any place where you had to guess. Guesses are fine if they are listed.
```
