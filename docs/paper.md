# ecog-lakehouse in one page

A lakehouse over public brain recordings, built to test three claims on real data. The claims, the method, the results and where the test stops.

## Problem

- Regulated teams keep the data and the proof of its rules apart. The proof is a document, and it ages the day it is written. The FDA software assurance guidance [5] accepts automated evidence instead.
- A number in a report rarely leads back to the bytes it came from. A lineage catalogue drifts from the data it describes.
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

**Checks.** `pipeline/checks.py` turns each row of `governance/requirements.csv` and each contract rule (Open Data Contract Standard v3 [6]) into plain SQL, one of eight kinds (`doc/spec.md` section 5.2). The rows quote 21 CFR Part 11 [1], ISO 13485 [2], ALCOA+ [3] and GDPR Article 9 [4]. The mapping of clauses to checks is illustrative and has not been reviewed by a compliance professional. Each run appends one evidence row per check with the dataset version (a digest of the file digests), the engine version and the git commit. A `block` failure stops the build. The browser reruns the same SQL with DuckDB-WASM.

**Lineage identifier.** `lid` is 128 bits in the ULID layout [7]: 48 bits of first ingestion time, then layer, experiment, file, run, channel, segment and the radioactive bit that marks a canary (`doc/spec.md` section 12.1). Decoding is a bit shift; the source file and its sha256 are one join away. Against other schemes:

| Scheme | What it encodes | What a decode needs | Cost per record |
|---|---|---|---|
| `lid` | 48 bit time, layer, experiment, file, run, channel, segment, radioactive bit | Bit shift for the fields; one join for the file path and sha256 | 16 bytes |
| ULID [7] | 48 bit millisecond time, 80 random bits | Bit shift for the time; the rest carries no meaning | 16 bytes, 26 characters as text |
| UUIDv7 [9] | 48 bit Unix millisecond time, version and variant, 74 bits random or counter | Bit shift for the time | 16 bytes |
| OpenLineage [10] | Run events: run id, job, input and output datasets, facets | A query over stored events, at dataset and column grain | None; events per run |
| W3C PROV [11] | Entities, activities, agents and relations such as `wasDerivedFrom` | A graph query over the relations | One entity and its relations per item tracked |

**Planted faults.** Each fault under `faults/<letter>/` has a plant, a fix and a `bench.sh`; the pipeline holds the fixed version. Timings are shell wall clock over HTTP to GitHub Pages. Faults A, D and G run on the DuckDB 2.0 alpha CLI, Fault F on the pipeline's DuckDB 1.5.5. Fault A takes the median of three runs, D and G one run, F ten attempts per setting.

## Results

Checks, evidence run `01M3WTDATJYQ57CY5YHT2D54NR` of 2026-10-01, queried from `gold/evidence`:

| Checks run | Passed | Failed, `flag` | Failed, `block` | Error |
|---|---|---|---|---|
| 111 | 108 | 3 | 0 | 0 |

The three flags are plausibility checks under ALCOA+ Accurate. Two are on `gold/channel_quality`, 101 and 48 of 2241 records. One is on `gold/experiment_summary`, 1 of 42 rows. A flag reports records and lets the build continue.

Faults, copied from `docs/bench.md`, run of 2026-10-04 over GitHub Pages; Fault A times are the median of three:

| Fault | Mistake | Fix | Before | After |
|---|---|---|---|---|
| A | One row group, 49.55 MiB | 2 files, 37 sorted row groups, Parquet version 2, 17.45 MiB | One record 1.05 s, aggregate 1.43 s | One record 0.38 s, aggregate 1.00 s |
| D | A Python loop downloads 11 files one at a time | One `read_parquet` over every URL | 6.60 s | 0.64 s |
| F | 503 on one range request in ten, `http_retries = 0` | `http_retries = 8`, backoff 2 | 0/10 reads succeed | 10/10 |
| G | Generated SQL nests 512 `OR`s | An `IN` list | `EXPLAIN` 0.08 s | `EXPLAIN` 0.04 s |

For Fault A the fixed layout wins the lookup it was built for, 487.8 KiB received against 16.3 MiB, and costs the aggregate no bytes, 16.1 MiB against 16.3 MiB. An earlier alpha build received 72.7 MiB for that aggregate. `docs/lessons-learned.md` section 8 traces it to that build's file cache.

## Limits

| Limit | Effect |
|---|---|
| One dataset | Three experiments of one library. Another source may behave differently. |
| One machine | Every timing comes from one WSL virtual machine. |
| One network location | Every remote read takes one path to GitHub Pages. Another CDN edge gives other times. |
| An alpha engine | The fault benches run on a DuckDB 2.0 alpha build, named with its sha256 in `docs/bench.md`. Fault A's result changed between two alpha builds. |
| One author | No independent review of design, code or results. |
| `faces_basic` unit scale | The source does not document it. Those rows are marked `scale_basis = assumed`. |
| Three runs | Fault A reports min, median and max of three runs, D and G one run. |

## References

1. eCFR, 21 CFR Part 11, Electronic Records; Electronic Signatures. https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11
2. ISO 13485:2016, Medical devices, Quality management systems, Requirements for regulatory purposes. https://www.iso.org/standard/59752.html
3. FDA, Data Integrity and Compliance With Drug CGMP, Questions and Answers, December 2018. It defines ALCOA; the term ALCOA+ does not appear in it. https://www.fda.gov/regulatory-information/search-fda-guidance-documents/data-integrity-and-compliance-drug-cgmp-questions-and-answers
4. Regulation (EU) 2016/679, General Data Protection Regulation, Article 9. https://eur-lex.europa.eu/eli/reg/2016/679/oj
5. FDA, Computer Software Assurance for Production and Quality Management System Software, final guidance, February 2026. https://www.fda.gov/regulatory-information/search-fda-guidance-documents/computer-software-assurance-production-and-quality-management-system-software
6. Bitol, Open Data Contract Standard, v3. https://bitol-io.github.io/open-data-contract-standard/latest/
7. ULID specification. https://github.com/ulid/spec
8. Miller, K. J. A library of human electrocorticographic data and analyses. Nature Human Behaviour 3, 1225 to 1235 (2019). https://doi.org/10.1038/s41562-019-0678-3
9. RFC 9562, Universally Unique IDentifiers (UUIDs), section 5.7, UUID Version 7. https://www.rfc-editor.org/rfc/rfc9562.html
10. OpenLineage, object model. https://openlineage.io/docs/spec/object-model
11. W3C, PROV-DM: The PROV Data Model, Recommendation, 30 April 2013. https://www.w3.org/TR/prov-dm/
