# REVIEW.md

One entry per phase. What was checked, what failed, what changed.

## Phase 0, skeleton

- Status: done, 2026-09-19, branch `feat/phase0`, eleven commits after the scaffold, merged to master as pull request 1, `89c0ce1`
- Environment: WSL2 Ubuntu 26.04, Python 3.14.4, DuckDB 1.5.5, scipy 1.18.1, PyYAML 6.0.3, pytest 9.1.1, ruff 0.16.8

### Checked

- `make all SYNTH=1` from a clean clone in `/tmp`, fresh venv and fresh `DATA_DIR`, no network: Bronze 23,040,000 rows from six synthetic files, Silver, Gold, 89 checks, all pass, publish of four Gold datasets. Output below.
- `make test` in the same clone: 48 tests. Lineage round trip per field and at field maxima, 26 character Crockford text, `lid_parse(lid_text(x)) = x`, Python ULID and SQL text agree, `lid_parent`, `lid_children` returns exactly one ingest's records, `lid_trace` on a Bronze row returns the audit's `source_path`, `source_url`, `sha256`. Bronze schema equals spec 3.1 column by column and type by type. Silver files sorted by `lid, sample_idx`, row groups under 200,000 and at least two per file, no `subject_src` in any Silver or Gold view, re-identification writes `access_log` before answering, a rerun adds no pseudonym. Gold counts, missing samples equal to the NaN bursts, channels with an injected 50 Hz tone rank above the others on `line_noise_ratio`, NULL under 10 s. Every contract's columns and types equal the Parquet written. One unit test per check kind, all eight. Evidence is append-only across two runs, `dataset_version` identical for identical inputs. `no_direct_identifier` fails when `subject_src` is leaked into Silver. The generator rejects malformed SQL and 40 levels of nested parentheses.
- A second `make all SYNTH=1` on the same `DATA_DIR`: Bronze skipped every file by sha256, Silver and Gold rebuilt, evidence appended.
- `git status --short` before every commit: nothing under `data/`, `docs/data/` or any `.duckdb`, `.parquet`, `.mat`. Every commit passed `make lint` and `make test`.

### Failed, and fixed before the commit

- DuckDB binds a macro body at creation, so `lid_trace` and `lid_children` could not be created before `lineage_dim` and `silver_record` existed. `db.connect()` now creates a typed empty view for every dataset with a known schema (Bronze inline, Silver and Gold from their contract) before loading `sql/lineage.sql`.
- DuckDB 1.5 has no cast between `UUID` and any integer. `lid_u128` goes through `from_hex(...)::BIT::UHUGEINT`, `lid_from_u128` through `hex()` padded to 32 characters.
- A partitioned `COPY ... ORDER BY` wrote the first sorted chunk of a file last, with one thread as well as with twelve. `silver/recording` is written with one plain `COPY` per partition, which keeps the order. The sortedness test caught it.
- DuckDB rounds `ROW_GROUP_SIZE 200000` up to 200,704, which fails `partition_layout max 200000`. The writer asks for 198,656.
- Hive partition columns come back after the file columns and a numeric looking `subject_pid` was typed BIGINT. Partitioned writes use `WRITE_PARTITION_COLUMNS`, every read uses `hive_types_autocast = false`. The Bronze schema test caught the order.
- `pip install -e ".[dev]"` refused the flat layout. `pyproject.toml` names the `pipeline` package.
- A `sql` check whose placeholder was also named `sql` collided with the renderer's own argument. The placeholder is `{{query}}`.
- A rerun of `make silver` with no new subject called `executemany` with an empty list. Found by the second `make all`, not by the tests; a test now covers it.
- `str` hashing is randomised per process, so the synthetic seed used `zlib.crc32`.

### Changed in doc/spec.md, forced by the code or by a contradiction

- 3.2 `silver/recording`: sorted by `lid, sample_idx` (section 12.2 and the phase 0 prompt said so, section 3.2 and the Fault A fix said `channel_idx, ts_ms`); `lid` and `sample_idx` added to the column table; row groups of at most 200,000 rows, written as 198,656.
- 3.2 `silver/record`: schema added, `lid, experiment, subject_pid, run, channel_idx, n_samples_src`. Section 12.2 named the dataset without columns.
- 6 Fault A fix: `ORDER BY (lid, sample_idx)`, `ROW_GROUP_SIZE 198656`, and the v1.x form is one plain `COPY` per partition with the reason.
- 12.1 `ingest_ord`: position of the file in the append-only `ingest_audit`, ordered by `ingested_at` then `sha256`. A lexical rank of sha256 changes when a later file sorts before an existing one, and Bronze rows are immutable.
- 12.2 `lineage_dim`: `experiment` column added, taken from the Bronze recording partition, needed by `lid_prefix_lo` and `lid_prefix_hi`.
- No ADR changed. ADR-0005 not needed.

### Guesses

- Synthetic files are MATLAB v5 written by `scipy.io.savemat` with the fields a Stanford file has (`data`, `stim`, `locs`), plus `experiment`, `subject`, `run`, `srate`, `brain_area`. Amplifier unit is 0.1 microvolt per raw unit; the map from experiment to unit lives in `convert_mat.UV_PER_UNIT` and Silver applies it.
- The adapter registry is keyed by the directory under `raw/`: `synthetic` in phase 0, experiment names in phase 1.
- A file whose sha256 is already in `ingest_audit` is skipped. Otherwise a rerun duplicates Bronze and `unique lid` on `silver/record` fails. `synth.py` keeps an existing file for the same reason: the MATLAB header carries a creation time.
- `bronze/event` rows carry a `lid` with channel 0, because an event belongs to the run, not to a channel.
- `clipped_pct` takes the run's observed extremes of `value_uv` as the amplifier rails; Silver has no amplifier range.
- `duration_s` is the sum over runs of the last present sample time plus one millisecond.
- `experiment_summary` carries no `lid`; its grain spans records and section 12.2 does not list it.
- `check_id` is `requirement_id/check_kind/dataset` followed by the parameter values, so two rows of the same requirement stay distinct.
- Contract `required` and `unique` properties and every `quality` rule with `engine: ecog-lakehouse` generate checks with framework `contract`, because spec section 4 says the generator reads the contracts. That is 81 of the 89 evidence rows.
- `retention` takes the oldest Parquet modification time from Python, because DuckDB 1.5 exposes no file time in SQL.
- `make all` includes `publish`, so `pipeline/publish.py` exists in phase 0: Gold copied to `docs/data/gold/`, `manifest.json` with bytes and sha256 per file, limits of section 9 enforced. No site, no fault files.
- `gold/evidence` is one file per run under `run_id=<ulid>/`, never rewritten.

### Not in phase 0

`fetch.py`, real adapters, `sql/lineage_pg.sql`, faults, `docs/index.html`, `docs/data/checks.json`, git hooks (`CLAUDE.md` describes them, none are installed; `make lint` and `make test` were run by hand before every commit).

### Verifier output

Clean clone inside WSL, fresh venv, fresh `DATA_DIR`, run at commit `1ff7cd8`, the last code commit; the docs commit that adds this entry came after. `make lint` printed `result: pass` for every document and exited 0.

```
$ git clone -q -b feat/phase0 <checkout> /tmp/ecog-lakehouse_verify
$ git log --oneline | head -1
1ff7cd8 fix(silver): rerun with no new subject adds no pseudonym
$ python3 -m venv --without-pip /tmp/ecog-lakehouse_verify_venv
$ pip --python /tmp/ecog-lakehouse_verify_venv/bin/python install -e .[dev]
$ export DATA_DIR=/tmp/ecog-lakehouse_verify_data
$ make all SYNTH=1
python3 pipeline/run.py bronze --synth
convert: 23040000 rows written
python3 pipeline/run.py silver
run: keyring, 3 new pseudonyms
run: silver/010_subject.sql
run: silver/020_record.sql
run: silver/030_recording.sql, 6 partitions
run: silver/040_electrode.sql
run: silver/050_event.sql
python3 pipeline/run.py gold
run: line noise on 384 records
run: gold/010_channel_quality.sql
run: gold/020_experiment_summary.sql
run: gold/030_feature_window.sql
python3 pipeline/checks.py
checks: run 01M2WZK8K54TZMGHBK5KFMQCYZ, {'pass': 89, 'fail': 0, 'error': 0}
python3 pipeline/publish.py
publish: 4 files, 301154 bytes, manifest at /tmp/ecog-lakehouse_verify/docs/data/manifest.json
make all exit 0
$ make test
python3 -m pytest -q
................................................                         [100%]
48 passed in 8.35s
make test exit 0
$ git status --short
$ du -sh $DATA_DIR/*
165M	/tmp/ecog-lakehouse_verify_data/bronze
300K	/tmp/ecog-lakehouse_verify_data/gold
780K	/tmp/ecog-lakehouse_verify_data/keyring.duckdb
89M	/tmp/ecog-lakehouse_verify_data/raw
264M	/tmp/ecog-lakehouse_verify_data/silver
$ python -c "import duckdb; print(duckdb.__version__)"
1.5.5
```

## Phase 0 amendment, lid layout from arch-standards

- Status: done, 2026-09-20, branch `feat/lid-layout` on top of the merged phase 0, spec commits `957efe5` and `d6acc21` merged in, merged to master as pull requests 2 and 4, `5e136b0` and `747ea27`
- Environment: as phase 0, arch-standards at `../arch-standards` on branch `feat/ids-open-items`

### Checked

- `sql/lineage/lid_generated.sql` is byte identical to `arch-standards/ids/generated/lid/duckdb.sql`, copied by `make lineage`, never edited. Encode, decode, every field accessor, validate and the UUID bridge come from it. `sql/lineage/lid_extras.sql` hand writes only the lineage tables, text form and parse, `lid_relayer`, `lid_parent`, `lid_prefix_lo`, `lid_prefix_hi`, `lid_children`, `lid_trace`.
- Every loader relayers through `lid_relayer`, which calls `lid_validate` on the layer being read and errors on a mismatch. A test proves the error.
- Layout tests: round trip per field including the canary bit, no field straddles the 64 bit boundary (hi and lo words checked separately), text and parse, Python ULID and SQL text agree, parent, children, trace.
- Canary records, spec 12.5: a fourth synthetic subject carries the radioactive bit from Bronze on, is present in Silver, absent from every Gold mart, two `sql` requirement rows assert it, `publish` refuses a file holding one. Tests for each.
- `gold/dataset_manifest`, spec 3.3: one row per dataset per Gold build, `dataset_version` equal to the digest the checks use, `lid_lo` and `lid_hi`, source file digests through `lineage_dim`. Contract and test.
- Verifier on a clean clone, fresh venv and `DATA_DIR`: 30,720,000 Bronze rows, 102 checks pass, 55 tests, output below.

### Failed, and fixed before the commit

- The generated `lid_to_uuid` and `lid_from_uuid` used casts DuckDB 1.5.5 does not implement. Fixed in arch-standards `idgen` (hex bridge) with a round trip test there, regenerated, copied. The hand written bridge that stood in meanwhile is gone.
- Windows git converted checkouts to CRLF and made two files look modified. Local `core.autocrlf=false` in both repositories, nothing committed for it.
- Two test bugs of my own: a wrong shift in the hi word assertion, and the canary subject sorting before `cc`.

### Changed

- `doc/spec.md` 12.1: layout table from the merge; the `file` line keeps the phase 0 wording, position in the append-only audit, so `ingest_ord` stays stable.
- `Makefile`: `lineage` target, `ARCH_STANDARDS ?= ../arch-standards`.
- `doc/agent/phase0.md`: amendment paragraph naming what step 3 now means and the two spec sections in scope.
- No ADR changed. ADR-0005 not needed.

### Guesses

- The canary subject is source code `canary` in `pipeline/synth.py`, listed in `convert_mat.CANARY_SUBJECTS`; the bit is set at Bronze conversion so `lid_parent` chains stay consistent.
- The `docs/data` half of the canary rule is enforced by `publish` refusing the copy, not by an evidence row, because on a first run `docs/data` is empty and a `sql` check over missing files would error.
- `gold/dataset_manifest` is rewritten per build, not appended; its grain is `dataset_version` and an identical rebuild repeats the version.
- The generated `lid_encode` has no range guard, so the phase 0 out of range test was dropped. Rule 7 of the ids SPEC says encode range checks; worth a rule in `idgen` for the SQL targets.
- `experiment_summary` still carries no `lid`, so canary subjects are filtered by `subject_pid` there.

### Verifier output

```
$ git clone -q -b feat/lid-layout <checkout> /tmp/ecog-lakehouse_verify
$ git log --oneline | head -1
853fa52 refactor(lineage): take the UUID bridge from the generated macros
$ cmp sql/lineage/lid_generated.sql ../arch-standards/ids/generated/lid/duckdb.sql && echo identical
identical
$ python3 -m venv --without-pip /tmp/ecog-lakehouse_verify_venv
$ pip --python /tmp/ecog-lakehouse_verify_venv/bin/python install -e .[dev]
$ export DATA_DIR=/tmp/ecog-lakehouse_verify_data
$ make lint | grep -c "result: pass"
20
$ make all SYNTH=1
python3 pipeline/run.py bronze --synth
convert: 30720000 rows written
python3 pipeline/run.py silver
run: keyring, 4 new pseudonyms
run: silver/010_subject.sql
run: silver/020_record.sql
run: silver/030_recording.sql, 8 partitions
run: silver/040_electrode.sql
run: silver/050_event.sql
python3 pipeline/run.py gold
run: line noise on 512 records
run: gold/010_channel_quality.sql
run: gold/020_experiment_summary.sql
run: gold/030_feature_window.sql
run: gold/dataset_manifest, 12 datasets
python3 pipeline/checks.py
checks: run 01M2ZJ68ZR1KCD78GVFS23EVM4, {pass: 102, fail: 0, error: 0}
python3 pipeline/publish.py
publish: 5 files, 306033 bytes, manifest at /tmp/ecog-lakehouse_verify/docs/data/manifest.json
make all exit 0
$ make test
python3 -m pytest -q
.......................................................                  [100%]
55 passed in 9.36s
make test exit 0
$ git status --short
$ du -sh $DATA_DIR/*
218M	/tmp/ecog-lakehouse_verify_data/bronze
308K	/tmp/ecog-lakehouse_verify_data/gold
780K	/tmp/ecog-lakehouse_verify_data/keyring.duckdb
119M	/tmp/ecog-lakehouse_verify_data/raw
352M	/tmp/ecog-lakehouse_verify_data/silver
```

## Phase 0 amendment, text, parse and relayer from the generator

- Status: done, 2026-09-20, branch `feat/lid-generated-macros` on top of `feat/lid-layout`, merged as pull request 3, `f951eed`, and reached master through pull request 4
- Environment: as phase 0, arch-standards at `../arch-standards` on branch `feat/ids-text-parse-relayer`, its pull requests 2 and 3 open

### Checked

- `sql/lineage/lid_generated.sql` is byte identical to `arch-standards/ids/generated/lid/duckdb.sql` after `make lineage`. It now carries `lid_text`, `lid_parse` and `lid_relayer` as well, 17 macros in total.
- `sql/lineage/lid_extras.sql` hand writes only the lineage tables and the navigation: `lid_parent`, `lid_prefix_lo`, `lid_prefix_hi`, `lid_children`, `lid_trace`. Nothing in it touches a bit position except `lid_parent`, which subtracts one layer.
- The five loaders still go through `lid_relayer`, now the generated one, which validates the layer being read before incrementing it. The mismatch error is still proved by a test.
- Clean clone, `ruff` clean, 20 documents lint clean, 30,720,000 Bronze rows, 102 checks pass and 0 fail, 55 tests. Output below.

### Failed, and fixed before the commit

- Nothing failed. The swap is type driven: the generated macros take and return `UHUGEINT` while `lid` is stored as `UUID`, so the five loaders and three test assertions wrap with `lid_from_uuid` and `lid_to_uuid`. Caught by writing it, not by a red test, because the hand written macros were shadowing the generated ones by name until they were deleted.

### Changed

- `sql/lineage/lid_extras.sql`: `lid_text`, `lid_parse` and `lid_relayer` deleted, they are generated now.
- `sql/silver/020_record.sql`, `040_electrode.sql`, `050_event.sql`, `sql/gold/010_channel_quality.sql`, `030_feature_window.sql`: `lid_relayer` calls wrapped for the UUID boundary.
- `tests/test_lineage.py`: same wrapping in the text, parse and relayer assertions.
- `doc/spec.md` 12.1 and 12.3, forced by a contradiction with the code. 12.3 named `sql/lineage.sql` and a PostgreSQL twin `sql/lineage_pg.sql`, neither of which exists; it gave `lid_encode` 7 arguments where the layout has 8 including the canary bit; it called the decode key `ingest_ord` where the generated struct says `file`. The code was right in all three, the spec was stale. The table now has a `Source` column saying which macros are generated and which are this system's own, and `lid_relayer`, `lid_validate`, `lid_to_uuid` and `lid_from_uuid` are listed.
- No ADR here. The decision to generate `relayer` is arch-standards ADR-0002, because that is where the rule and the naming table live.

### Guesses and open points

- `lid_relayer` returning the native integer rather than `UUID` is the generator's contract, so this system wraps at five call sites. More verbose than the hand written macro it replaces, and it keeps one home for the bit work. Reversing that would mean the generator knowing a project's storage type, which it does not.
- The range guard gap from the previous entry is still open. Ids SPEC rule 7 says every input field is range checked on encode; the Python target does it, the SQL targets do not, so `lid_encode` in DuckDB still wraps a value that is out of range instead of erroring. It belongs in `idgen`, not here.
- The verifier reused `<venv>`, whose editable install points at `<checkout>`. `pipeline/db.py` sets `REPO` from the `pipeline` module's own location, so `publish` wrote its manifest into the original checkout rather than the clone. The clone's data and checks were unaffected and the original repository stayed clean, but a verifier run is only truly isolated with a venv installed from the clone, as the previous entry did.

### Verifier output

```
$ git clone -q -b feat/lid-generated-macros <checkout> /tmp/ecog-lakehouse_verify
$ git log --oneline | head -1
d58cbcf refactor(lineage): take text, parse and relayer from the generated macros
$ cmp sql/lineage/lid_generated.sql ../arch-standards/ids/generated/lid/duckdb.sql && echo identical
identical
$ export DATA_DIR=/tmp/ecog-lakehouse_verify_data
$ ruff check .
All checks passed!
$ python scripts/lint_doc.py ... | grep -c "result: pass"
20
$ make all SYNTH=1        # recipes run directly, make is not installed in this WSL
convert: 30720000 rows written
run: silver/050_event.sql
run: gold/dataset_manifest, 12 datasets
checks: run 01M2ZJVD4E594S7N12R9SWSXB4, {'pass': 102, 'fail': 0, 'error': 0}
publish: 5 files, 306037 bytes
$ python -m pytest -q
.......................................................                  [100%]
55 passed in 10.00s
$ git status --short
```
