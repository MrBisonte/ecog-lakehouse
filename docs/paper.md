# ecog-lakehouse in one page

A lakehouse over public brain recordings, built to test three claims on real data. This page states the claims, the method, the results and where the test stops.

## Problem

- Regulated data teams keep the data and the proof of its rules apart. The proof is a document, and it ages the day it is written.
- A number in a report rarely leads back to the bytes it came from. A lineage catalogue can drift from the data it describes.
- File layout is chosen once and seldom measured.

## Contribution

| Claim | What it means here |
|---|---|
| Governance executes | A regulation clause is a CSV row. The build turns it into SQL, runs it and keeps the result as an evidence row. |
| Every number traces to bytes | Every record carries an identifier that decodes to its source file. Every source file carries a sha256. |
| File layout is a performance decision | Four planted faults, each a layout or access mistake, each measured before and after its fix. |

## Method

Data: three experiments of the Stanford ECoG library, `fingerflex`, `motor_basic` and `faces_basic`, MATLAB files at 1 kHz.

| Layer | Holds | Rule |
|---|---|---|
| Bronze | Raw samples, the sha256 of each source file | Append only |
| Silver | Microvolts, milliseconds, pseudonyms | No source subject code |
| Gold | Channel quality, experiment summary, one second windows, evidence | Every value is a query result |

**Check generator.** `pipeline/checks.py` reads `governance/requirements.csv` and the data contracts. Each rule names one of eight check kinds (`doc/spec.md` section 5.2) and renders as plain SQL. Each run appends one evidence row per check, with the dataset version, the engine version and the git commit. The dataset version is a digest of the file digests. A `block` failure stops the build. The same SQL is published and rerun in the browser by DuckDB-WASM.

**Lineage identifier.** `lid` is 128 bits in the ULID layout: 48 bits of first ingestion time, then layer, experiment, ingested file, run, channel, segment and a canary bit (`doc/spec.md` section 12.1). Decoding is a bit shift. The file behind a Gold row is one join to `lineage_dim`, one row per ingested file. Every record of one file is a range scan on the prefix.

**Planted faults.** Each fault under `faults/<letter>/` has a plant, a fix and a `bench.sh`. The pipeline holds the fixed version.

**How measured.** Wall clock from the shell. Reads go over HTTP to GitHub Pages. Faults A, D and G run on the DuckDB 2.0 alpha CLI, Fault F on the pipeline's DuckDB 1.5.5. Fault A takes the median of three runs, D and G one run, F ten attempts per setting.

## Results

Checks, evidence run `01M3WTDATJYQ57CY5YHT2D54NR` of 2026-10-01, queried from `gold/evidence`:

| Checks run | Passed | Failed, `flag` | Failed, `block` | Error |
|---|---|---|---|---|
| 111 | 108 | 3 | 0 | 0 |

The three flags are plausibility checks under ALCOA+ Accurate. Two are on `gold/channel_quality`, 101 and 48 of 2241 records. One is on `gold/experiment_summary`, 1 of 42 rows. A flag reports records and lets the build continue.

Faults, copied from `docs/bench.md` at commit `39f241e`, the last section of each fault:

| Fault | Mistake | Fix | Before | After |
|---|---|---|---|---|
| A | One row group, 51960395 bytes | 2 files, 38 sorted row groups, 76269314 bytes | One record 1.708 s, aggregate 1.504 s | One record 0.649 s, aggregate 3.760 s |
| D | A Python loop downloads 8 files one at a time | One `read_parquet` over every URL | 9.457 s | 0.583 s |
| F | 503 on one range request in ten, `http_retries = 0` | `http_retries = 8`, backoff 2 | 0/10 reads succeed | 10/10 |
| G | Generated SQL nests 512 `OR`s | An `IN` list | `EXPLAIN` 0.093 s | `EXPLAIN` 0.046 s |

Fault A did not go as planned. The fixed layout wins the lookup it was built for and loses the full aggregate, which receives 72.7 MiB against 21.5 MiB. The cause is in `docs/lessons-learned.md` section 8.

## Limits

| Limit | Effect |
|---|---|
| One dataset | Three experiments of one library. Another source may behave differently. |
| One machine | Every timing comes from one WSL virtual machine. |
| One network location | Every remote read takes one path to GitHub Pages. Another CDN edge gives other times. |
| One author | No independent review of design, code or results. |
| `faces_basic` unit scale | The source does not document it. Those rows are marked `scale_basis = assumed`. |
| Median of three | Fault A reports a median of three runs, D and G one run. No spread is reported. |
