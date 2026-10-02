# ecog-lakehouse in one page

A lakehouse over public brain recordings, built to test three claims on real data. This page states the claims, the method, the results and where the test stops.

## Problem

- Regulated data teams keep the data and the proof of its rules apart. The proof is a document, and it ages the day it is written.
- The FDA computer software assurance guidance [5] accepts risk based, automated evidence.
- A number in a report rarely leads back to the bytes it came from. A lineage catalogue can drift from the data it describes.
- File layout is chosen once and seldom measured.

## Contribution

| Claim | What it means here |
|---|---|
| Governance executes | A regulation clause is a CSV row. The build turns it into SQL, runs it and keeps the result as an evidence row. |
| Every number traces to bytes | Every record carries an identifier that decodes to its source file. Every source file carries a sha256. |
| File layout is a performance decision | Four planted faults, each a layout or access mistake, each measured before and after its fix. |

## Method

Data: three experiments of the Stanford ECoG library [8], `fingerflex`, `motor_basic` and `faces_basic`, MATLAB files at 1 kHz.

| Layer | Holds | Rule |
|---|---|---|
| Bronze | Raw samples, the sha256 of each source file | Append only |
| Silver | Microvolts, milliseconds, pseudonyms | No source subject code |
| Gold | Channel quality, experiment summary, one second windows, evidence | Every value is a query result |

**Check generator.** `pipeline/checks.py` reads `governance/requirements.csv` and the data contracts (Open Data Contract Standard v3 [6]). The requirement rows quote 21 CFR Part 11 [1], ISO 13485 [2], ALCOA+ [3] and GDPR Article 9 [4]. The mapping of clauses to checks is illustrative and has not been reviewed by a compliance professional. Each rule names one of eight check kinds (`doc/spec.md` section 5.2) and renders as plain SQL. Each run appends one evidence row per check, with the dataset version, the engine version and the git commit. The dataset version is a digest of the file digests. A `block` failure stops the build. The same SQL is published and rerun in the browser by DuckDB-WASM.

**Lineage identifier.** `lid` is 128 bits in the ULID layout [7]: 48 bits of first ingestion time, then layer, experiment, ingested file, run, channel, segment and a canary bit (`doc/spec.md` section 12.1). Decoding is a bit shift. The file behind a Gold row is one join to `lineage_dim`, one row per ingested file. Every record of one file is a range scan on the prefix.

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

## References

1. eCFR, 21 CFR Part 11, Electronic Records; Electronic Signatures. https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11
2. ISO 13485:2016, Medical devices, Quality management systems, Requirements for regulatory purposes. https://www.iso.org/standard/59752.html
3. FDA, Data Integrity and Compliance With Drug CGMP, Questions and Answers, December 2018. It defines ALCOA; the term ALCOA+ does not appear in it. https://www.fda.gov/regulatory-information/search-fda-guidance-documents/data-integrity-and-compliance-drug-cgmp-questions-and-answers
4. Regulation (EU) 2016/679, General Data Protection Regulation, Article 9. https://eur-lex.europa.eu/eli/reg/2016/679/oj
5. FDA, Computer Software Assurance for Production and Quality Management System Software, final guidance, February 2026. https://www.fda.gov/regulatory-information/search-fda-guidance-documents/computer-software-assurance-production-and-quality-management-system-software
6. Bitol, Open Data Contract Standard, v3. https://bitol-io.github.io/open-data-contract-standard/latest/
7. ULID specification. https://github.com/ulid/spec
8. Miller, K. J. A library of human electrocorticographic data and analyses. Nature Human Behaviour 3, 1225 to 1235 (2019). https://doi.org/10.1038/s41562-019-0678-3
