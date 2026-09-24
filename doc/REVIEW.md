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
## Phase 1, real data

- Status: done, 2026-09-21, branch `feat/phase1`, fourteen commits after the merge of #4, not merged
- Environment: as phase 0, WSL2 Ubuntu 26.04, Python 3.14.4, DuckDB 1.5.5, scipy 1.18.1, 15 GB of RAM in the WSL VM, 12 GB DuckDB memory limit
- Spec: patch 0003 (NWB and BIDS on the roadmap, 3.4 Export) applied as `86dc21e`; patches 0001 and 0002 were already on master as `957efe5` and `d6acc21`, so "reach 9acef75" is satisfied by content

### Pre-flight

- `origin/master` at `747ea27`, `git status --short` empty, `make all SYNTH=1 && make test` rerun: exit 0, 55 passed.
- `echo $DATA_DIR` prints nothing in a login shell; the Makefile exports `$(HOME)/data/ecog-lakehouse` and every pipeline call went through `make` or an explicit export. Free under `$HOME`: 952 GB.
- Sections 2, 3.4, 7 and 12 of the spec and plan phase 1 read after patch 0003.

### Source facts, from the repository and the files, not assumed

- Files at `https://stacks.stanford.edu/file/druid:zk881ps0522/<experiment>.zip`; the repository publishes md5 and sha1 only, sha256 computed after download. All 45 data files are MATLAB 5.0, none v7.3.
- Sampling rate 1000 Hz for every experiment (manuscript Methods and each README; `faces_basic` files carry it in `srate`). Bandpass 0.15 to 200 Hz, Synamps2.
- Units: `fingerflex` and `motor_basic` READMEs state 1 amplifier unit = 0.0298 microvolts. `faces_basic` README states no scale; the adapter takes 0.0298 because the manuscript states the same amplifiers and settings for every experiment. Guess, recorded in the adapter table.
- Third experiment: `faces_basic`, 14 subjects, one stim code per picture onset (1 to 50 house, 51 to 100 face, 101 interstimulus, mapped to no event).
- Electrode locations: `fingerflex` in the data file (`locs`, mm, `elec_regions` codes), `motor_basic` in `locs/<code>_electrodes.mat` (Talairach mm, no region), `faces_basic` in `locs/<code>_xslocs.mat` as MRI voxel indices, so `x_mm`, `y_mm`, `z_mm` are NULL there and `brain_area` comes from the Destrieux codes of `fhpred_master.m`.

### Checked

- Real download: 2,048,729,660 bytes in three zips over the Stanford host at about 1.4 MB/s; one stall at 359 MB of `motor_basic.zip`, resumed with a Range request.
- Clean `make all` in `DATA_DIR`: 45 files (42 subjects and 3 canaries), Bronze 871,160,120 rows; Silver 2,433 records of which 192 canary; Gold 2,241 channel_quality rows, 860,889 feature windows, 42 experiment_summary rows; 103 checks pass, 0 fail, 0 error; publish 5 files, 10,883,540 bytes. Gold, checks and publish took 208 s after the memory fix below.
- Verifier: see the output at the end. `make fetch && make all && make test` from a clean clone: fetch verified all three zips, `make all` exit 0 in 513 s, 103 checks pass, 68 tests pass, nothing untracked in the clone.
- `make test`: 68 tests, `make lint` green, before every commit; 13 commits.

### Failed, and fixed before the commit

- `gold/channel_quality` spilled to `.tmp` in the working directory, the repo on the Windows mount, and died with "Cannot allocate memory" on 262 million Silver rows. `temp_directory` is `DATA_DIR/tmp` (spec 7 puts every DuckDB working file there).
- The same mart then held 12.1 GB, the DuckDB limit, on 871 million rows, twice: once as written, once with insertion order preservation off. Cause: the join with the per run rails and the aggregate carried `experiment` and `subject_pid`, heap allocated strings, through every sample row, with a group estimate of 164 million. Both `channel_quality` and `feature_window` now aggregate by `lid` alone and take the labels from `silver/record` afterwards, one row per record. Same rows, same values, the synthetic Gold tests did not change.
- An aborted `COPY` left a zero byte `data_0.parquet`, and the next `db.connect()` failed on it. `views()` removes an empty Parquet file with a printed reason; tested.
- Staging a source without electrode locations called `float(None)`. Never exercised in phase 0; `faces_basic` exercised it. NULL now, tested.
- The `faces_basic` canary had no event labels. Added.
- The verifier's first run filled `/tmp`, a 7.6 GB tmpfs in this WSL, with the copied zips. It runs under `$HOME` now.

### Checks that fail on real data and are right to fail

None. 103 of 103 pass.

### Observations, not fixed

- `fingerflex` subject `mv` has one cue onset in its file (178,960 samples, `cue` holds 0 and 1 only); the task table notes truncated raw data for some patients. Bronze keeps what the file says: 1 event, 43 records.
- `motor_basic` subjects `gf` and `zt` carry stim codes 13 and 15 that the README does not document: 61 events with a NULL label.
- `faces_basic` subjects `aa`, `ha` and `jt` hold raw values up to 18.7 million on a few channels, beyond exact float32 (2^24). `value_raw` is FLOAT by spec, so those values are rounded to even integers in Bronze.
- `clipped_pct` uses the observed extremes of the run as rails, so a run with one huge artefact channel reports near zero clipping on the others. Real amplifier rails are not in the files.
- The WSL clock jumped by about an hour and a half during the first full build while the host was away, so the audit timestamps of that build are not a wall clock. The build wall clock in `docs/bench.md` comes from the verifier's single uninterrupted run.

### Not in phase 1

NWB adapter and export (ADR-0005 proposed, nothing imports `pynwb`), faults, the site, `docs/data/` committed content. Commits 4 (spill fix) and the Gold rewrite landed after the canary and manifest commits because the real data failures surfaced only in the full build; every commit is one logical change.

### Verifier output

Clean clone inside WSL under `$HOME`, fresh venv, fresh `DATA_DIR` with the three verified zips copied in so `make fetch` verifies and extracts without a second 2 GB download; the download path itself ran for real the same day. Run at commit `5ed73af`, the last code commit; the docs commits came after.

```
$ bash ~/verify_phase1.sh feat/phase1     # clone under $HOME, three verified zips copied into a fresh DATA_DIR
commit 5ed73af
duckdb 1.5.5 scipy 1.18.1
python3 pipeline/fetch.py
fetch: 3 of 3 files verified
fetch exit=0
all exit=0 seconds=513
convert: 871160120 rows written
run: silver/030_recording.sql, 45 partitions
run: silver/050_event.sql
run: line noise on 2433 records
run: gold/dataset_manifest, 12 datasets
checks: run 01M32SPQ2CVDTH7CNN3MS8WJYX, {'pass': 103, 'fail': 0, 'error': 0}
publish: 5 files, 10883387 bytes, manifest at ~/ecog-lakehouse_verify/docs/data/manifest.json
$ make test
....................................................................             [100%]
68 passed in 10.76s
$ git status --short
$ du -sh $DATA_DIR/bronze $DATA_DIR/silver $DATA_DIR/gold
5.6G    ~/ecog-lakehouse_verify_data/bronze
8.5G    ~/ecog-lakehouse_verify_data/silver
11M     ~/ecog-lakehouse_verify_data/gold
```

## Phase 2, faults and bench

- Status: done, 2026-09-21, branch `feat/phase2`, nine commits after the merge of #8, not merged
- Environment: as phase 1 for the pipeline, DuckDB 1.5.5; the benches run on the DuckDB CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`, installed from the official installer's staged alpha channel into `~/.local/duckdb-alpha`, no GitHub release exists yet
- Data: the phase 1 build in `DATA_DIR`, 45 files, 871,160,120 Bronze rows

### Checked

- `make bench` writes `docs/bench.md`: the counts table, then one section per fault with a before and after table, every number a query result or a timer. `make publish` after the benches lists 8 files, 139,113,249 bytes under `docs/data`, under the 500 MB limit; the largest, the Fault A single row group file, is 51,960,395 bytes, under 95 MB.
- Fault A: the v2.0 `COPY ... PARTITION_BY ... ORDER BY ... ROW_GROUP_SIZE 198656` writes a sorted file, checked by a window query over the output. The alpha warns about unquoted identifiers in `PARTITION_BY`, the syntax the spec gives.
- Fault D: both approaches count the same 863,287 rows over the five published files; one httpfs statement is about three times faster than the sequential loop on loopback.
- Fault F: on DuckDB 1.5.5, `http_retries = 0` fails the query whenever a range request meets a 503, and the tuned retries recover every attempt. The 2.0 alpha CLI retries a 503 on its own with `http_retries = 0` and fails only when every range request fails; reported as a third row rather than hidden.
- Fault G: the 512 level nested OR parses and binds in about twice the time of the IN list; the malformed variant gets the parser's message with the token underlined. The generator's guard rejects both bad variants, tested.
- `make lint` green, `make test` 71 tests before every commit.

### Failed, and fixed before the commit

- Python's stock `http.server` answers a Range request with the whole file. DuckDB printed "the server does not support HTTP range requests" and downloaded every file whole, so the first run of faults A and F measured nothing. `faults/serve.py`, a 50 line static server with Range support, replaces it; the test for the proxy serves through it too.
- The first Fault F bench timed each attempt with one run and counted success with another, doubling the proxy's request counter. One timed run per attempt now.
- `getenv()` exists in the CLI only; the Python attempts of Fault F splice the URL in as a literal.
- Single timings on loopback varied by a factor of three between runs of the same query. Fault A reports the median of three.
- `ruff` refused two `noqa` comments for a rule that is not enabled; removed.

### Observations, not fixed

- Loopback has no latency, so the async read-ahead of Fault A shows no gap between layouts here; the row group and sortedness columns show the layout difference, the seconds will only once `BASE_URL` points at GitHub Pages (phase 3).
- The "bad" file of Fault A is sorted, because it is read from the pipeline's sorted partition; the fault is the single row group and the missing partition columns, and the spec's "unsorted" would need an ORDER BY random() that makes the file larger.
- The 2.0 alpha's partitioned COPY produced 21, 24 and 25 row groups for the same 7,236,800 rows on three runs, a parallel writer deciding the split; each row group stays under the 198,656 limit.
- The WSL clock still jumps when the host sleeps; the counts table at the top of `docs/bench.md` keeps the verifier's numbers from phase 1.

### Not in phase 2

GitHub Pages and the site (phase 3), a verifier rerun of `make all` (the pipeline did not change; `publish.py` gained the fault file listing, covered by the existing publish test and `make bench` on the phase 1 build), the choice between rails per run and per record for `channel_quality` (open, Alex's call).

## Phase 3, site

- Status: done, 2026-09-22, branch `feat/phase3`, three commits after the merge of #9, not merged; GitHub Pages not yet enabled, Alex's call after this step
- Environment: as phase 1; DuckDB-WASM 1.32.0 from cdn.jsdelivr.net, pinned in `docs/index.html`; a local range capable server (`faults/serve.py` from phase 2) on 127.0.0.1 for the check below

### Checked

- `docs/index.html`, one file, system font stack, no request to any host but the page's origin and `cdn.jsdelivr.net` (the resource timing list in the browser shows those two hosts and no other). On load it reads `data/manifest.json` with a cache busting query, registers the Gold Parquet files for HTTP range reads, creates one view per Gold dataset, loads `data/lid.sql`, runs every check in `data/checks.json`, and renders the checks table, `experiment_summary` (42 rows), the 100 `channel_quality` records with the highest line noise ratio out of 2,241, the evidence runs the pipeline recorded, and the published files with their digests.
- In the browser over the phase 1 publish: 61 checks rerun, 61 pass, 0 fail, 0 error; the pipeline's own run in `gold/evidence` shows 103 of 103. The 42 checks the page does not rerun read `DATA_DIR` or the source files (`hash_match`, `partition_layout`, `retention`) or Silver and Bronze datasets the site does not publish.
- `pipeline/publish.py` writes `docs/data/checks.json`, the Gold checks of the kinds that need only the views, and `docs/data/lid.sql`, a copy of the generated lineage macros. `tests/test_gold.py` reruns every published check in a fresh DuckDB over the published files alone, the way the page does: pass.
- `make lint` green, `make test` 70 tests.

### Failed, and fixed before the commit

- Timestamps came back from Arrow as epoch milliseconds and rendered as numbers; columns ending in `_at` are formatted as UTC text.
- The evidence runs section was inserted into the DOM by the script; it is a static section now.

### Not in phase 3

Pages itself (Settings, Pages, source `master`, folder `/docs`; then "a stranger's browser" and `BASE_URL=https://... make bench` for the phase 2 tables with real latency), the fault files on the page (spec 7 lists them under `docs/data/faults`, the page reads Gold only), rails per run or per record for `channel_quality` (open).

## Phase 3 addendum, GitHub Pages

- Status: done, 2026-09-23, branch `docs/bench-pages`; Pages enabled on the private repository (GitHub Pro), site at https://mrbisonte.github.io/ecog-lakehouse/
- The page from the Pages origin: 61 checks rerun in the browser, 61 pass, 42 experiment_summary rows, 100 channel_quality rows shown of 2,241, 8 published files listed; resource timing lists `mrbisonte.github.io` and `cdn.jsdelivr.net` and no other host; no console errors.
- `docs/bench.md` rewritten from `BASE_URL=https://mrbisonte.github.io/ecog-lakehouse/data`, the four fault tables against real latency; the counts table at the top keeps the phase 1 verifier numbers.

### Failed, and fixed before the commit

- Pages serves one file with a different ETag from different Fastly edges (`6ab394b5-...` from MAD, `6ab394b4-...` from TOJ, seen with three HEAD requests). DuckDB sends the first ETag as If-Match on the next range request and gets a 412, "ETag changed after it was opened". `SET unsafe_disable_etag_checks = true` on every remote read of faults A, D and F; the sha256 in `manifest.json` stays the integrity check. DuckDB-WASM on the page did not hit it.
- The Fault A "after" layout is two files on Pages, the alpha's partitioned writer split the partition, and the bench measured one. It measures every file of a layout now, with a files column; against a remote it no longer replants, the published copy is what is measured.
- DuckDB 1.5.5 raised `UnicodeDecodeError`, not its own error, on one 503 body from the proxy in front of Pages; the Fault F attempts count any exception as a failure.

### Observations, not fixed

- Fault A over Pages reads the opposite way from the loopback run and from the story in spec 6: the single row group file, 52 MB, takes about 1.0 s and the partitioned, sorted layout of 38 row groups in 76 MB about 2.7 s, with `read_ahead_depth` making no difference either way. Each row group is a range request and each request is a CDN round trip; on this file and this network the request count dominates the parallelism. The layout still wins the partition_layout check and the range retrieval story (`lid_children` reads one row group, not the file); the wall clock claim needs a bigger file or a closer host. Recorded as measured.
- Fault D over Pages: 5.1 s for the sequential loop against 0.33 s for one statement over 15,336,887 rows in 8 files. Fault F: 0 of 10 without retries, 10 of 10 with. Fault G unchanged.

## Rename, 2026-09-23

2026-09-23: project renamed to ecog-lakehouse.

## Digests verified by consumers, 2026-09-24

- Status: done, branch `feat/verify-digests`, four commits after the merge of #15
- Alex's decision, option 3 of three: the sha256 in `manifest.json` is checked by the consumers that rely on it, not only displayed. Chosen after the ETag finding of the phase 3 addendum, where a server invented label failed on a correct file and a digest computed from the bytes was the check that held.

### Checked

- `faults/d/verify.sql`: after the fix statement, every published file is read once more in full with `read_blob` and its `sha256()` compared with the manifest, one query, two numbers, files and mismatches. Against Pages: 8 files, 0 mismatches, 9.4 s, timed apart from the 0.58 s fix statement because it downloads every byte. The before row, the sequential loop, stays at 9.5 s and checks nothing.
- `docs/index.html`: every Gold file the page read is fetched once more and hashed with SubtleCrypto; the files table gained a digest column, match or MISMATCH, and the status line counts them. Locally over the published copy: 5 Gold files hashed, 0 mismatch; fault files listed as not read. Two hosts, no console errors.
- `tests/test_faults.py`: `verify.sql` on local files gives (files, 0), then (files, 1) after one file is overwritten.
- `docs/bench.md` rewritten against `https://mrbisonte.github.io/ecog-lakehouse/data`, the renamed site. `make lint` green, `make test` 73 tests.

### Failed, and fixed before the commit

- The first cut put the digest check inside `fix.sql`; the after row then took 10.9 s and the 0.3 s gap of Fault D vanished into the download the hash needs. The check is its own file and its own column now.

## Plausibility checks and the evidence page, 2026-09-25

- Status: done, branch `feat/evidence-page`, on top of `e1f2bcb`.
- Alex's ask, five parts: checks that are allowed to fail, the frameworks that do not run in the browser, order and grouping in the checks table, lids as text, and a set of small fixes. Two decisions came back mid flight: the ingest audit gains the machine that captured the file, and it stores the data root with the path below it rather than the absolute path twice.

### The two implausible subjects, investigated before anything was built

- Asked: are `8728e2d4b6d6e219` (faces_basic, rms_uv 15,000 to 84,000) and `72d88db77f3716bb` (motor_basic, rms_uv about 1) an adapter bug or the data as published.
- Answer: the data, in both cases. No adapter change.
- `8728e2d4b6d6e219` has a Bronze `value_raw` RMS of 795,000 with extremes at plus and minus 18.7 million, against roughly 2,500 for the other faces_basic subjects; two further subjects of that experiment sit at 666,000 and 80,000. The adapter applies the one documented scale, 0.0298 microvolts per unit from the README of the other two experiments, to every file of the experiment, and `convert_mat.read_faces_basic` already records that the faces_basic README gives no scale of its own. Inventing a per subject factor would be inventing a number.
- `72d88db77f3716bb` is not unusual at the subject level: Bronze RMS 2,535, ordinary for motor_basic. Two of its 49 channels, run 1 channels 31 and 43, read 1.10 and 1.00 microvolts while the median channel reads 72.9. Two flat electrodes, not a unit error.
- Also seen while looking: many subjects clip at exactly plus and minus 32,767, the signed 16 bit limit, in the published files themselves.
- Both are now reported by the plausibility checks rather than by a person reading a table.

### Checked

- Rebuilt from the sources after the audit change, `make all` exit 0 in 355.6 s wall clock, first ingestion to last evidence row: 45 files, Bronze 871,160,120 rows, Silver 2,433 records, Gold 2,241 channel_quality rows, 860,889 feature windows, 42 experiment_summary rows. Publish 8 files, 139,116,833 bytes.
- 106 checks in that run: 103 pass, 3 fail, all three at severity `flag`, 0 blocking, so `make all` returns 0. The 45 `hash_match` rows that were failing before this branch now pass, because the check reads `source_path_rel` against the current root.
- The three flags on real data: 101 of 2,241 channels outside 1 to 1000 microvolts, 48 of 2,241 at or above 0.5 line noise, and 1 of 42 subjects outside the event rate band, `fingerflex 74ad3b8f18e75291`. The mart spans 0.996 to 84,441.9 microvolts, which is the pair of findings above seen from the other end.
- The page over the published copy, from a clean origin: 64 checks rerun, 61 pass, 3 flagged, 0 error; the coverage line reads 106 checks in the pipeline's run with 42 of them outside Gold; the framework table shows ALCOA+ 5 with 3 not passing, GDPR 9, ISO 13485 2, Part 11 2, ODCS contract 88; the three flags sort to the top and name their records; contract rules collapse to five `details` groups; `lid` reads `01M3AS9Q5W60R0008GA0000000`; 5 Gold files hashed in the browser, 0 mismatch. No console errors.
- `ruff` clean, 79 tests pass, `scripts/lint_doc.py` pass on every document.

### Failed, and fixed before the commit

- The first cut of the audit stored `source_path` and `source_path_rel` side by side, and Alex pointed out that the second is a suffix of the first, character for character. The audit now stores `data_root` and `source_path_rel` and stores the absolute path nowhere; `lineage_dim` composes it, so `lid_trace` is unchanged and a test asserts the composition. That cost the first rebuild, which was thrown away half way through Silver.
- A batch of edits written with `newline=""` silently matched nothing, because most files in this repository are CRLF and the search strings were LF. Three files were left unchanged while the script reported success, and the first full test run found it. Edits are applied one line at a time now, with an assertion per replacement.
- `expected` on a flag check was the empty string, which reads as missing data rather than as a requirement, on the page and in `gold/evidence` alike. Both sides say `no records` now, so a clean flag check reads `no records` against `no records` and a failing one reads its records against the same words.
- `keyring.host()` was memoised with `functools.cache`. The pseudonym derives from the secret of the keyring of the current `DATA_DIR`, so a cached answer carried one lakehouse's pseudonym into another's audit rows and the test suite caught it across two temporary directories. The cache is gone.

### Observed, not changed

- The rebuild starts a new evidence chain. `gold/evidence` is append-only within a lakehouse, and this one was rebuilt from the sources, so the published copy holds the runs of this lakehouse and none from before it. The previous build, Bronze, Silver, Gold and its evidence, is preserved outside the repository at `~/data/ecog-lakehouse-before-20260925-002704` and was not deleted.
- A returning visitor can see the digest column read MISMATCH for a few minutes after a republish. `manifest.json` is fetched with a cache buster and the Parquet files are not, so a browser holding the previous bytes compares them against the new digests. Seen here between two local origins and confirmed to be cache, not corruption: the same page from a clean origin reads 0 mismatch. Leaving the fix to Alex, since it is a caching decision.
