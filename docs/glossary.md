# Glossary

The words the other pages assume. The spec column names the section of [doc/spec.md](../doc/spec.md) that defines the term.

| Term | Meaning | Spec |
|---|---|---|
| ECoG | Electrocorticography. Electrodes placed on the surface of the cortex record brain activity. The source data is the Stanford ECoG library. | [2](../doc/spec.md#2-source-data) |
| Bronze | The first layer. Raw arrays, one row per sample, no cleaning. Append-only: a file once written is never modified. | [3.1](../doc/spec.md#31-bronze) |
| Silver | The second layer. Typed, timestamped and pseudonymised. The first layer a consumer may read. | [3.2](../doc/spec.md#32-silver) |
| Gold | The third layer, the model for consumers. Every value is a query result. | [3.3](../doc/spec.md#33-gold) |
| medallion | The name for the Bronze, Silver, Gold layering. All three layers are Hive partitioned Parquet. | [3](../doc/spec.md#3-layers) |
| lid | Lineage identifier. 128 bits in the ULID layout: a 48 bit timestamp, then layer, experiment, file, run, channel, segment and the radioactive bit. Decoding it needs no join. | [12](../doc/spec.md#12-lineage-identifier-lid) |
| record | One channel of one run of one ingested file, optionally split into segments. Each record has one `lid`. Samples reference their record. | [12](../doc/spec.md#12-lineage-identifier-lid) |
| channel | One electrode of a recording. `channel_idx` is its zero-based index in the source array. | [3.1](../doc/spec.md#31-bronze) |
| segment | A fixed part of one channel run, 0 when the run is not split. A run over 24 days at 1 kHz is split. | [12.1](../doc/spec.md#121-shape), [12.6](../doc/spec.md#126-limits) |
| run | The recording run within one experiment for one subject, from 1. Not the build: a check run is a `run_id`. | [3.1](../doc/spec.md#31-bronze) |
| canary | A planted fake subject, one per experiment. Its records carry the radioactive bit, which `lid_radioactive` reads. A check asserts none reaches Gold or `docs/data/`. | [12.5](../doc/spec.md#125-canary-records) |
| radioactive bit | Bit 23 of `lid`, set on every canary record. Used only as the name of the bit and of the macro `lid_radioactive`. | [12.1](../doc/spec.md#121-shape) |
| rails | The clipping bounds of a run: the lowest and highest value observed in the run, one pair for every channel of the run. `clipped_pct` is the share of samples on them. | [3.3](../doc/spec.md#33-gold) |
| contract | One YAML file per Silver and Gold dataset under `contracts/`, in the Open Data Contract Standard v3. Columns, types, `required`, `unique` and a `quality` block. | [4](../doc/spec.md#4-contracts) |
| requirement | One row of `governance/requirements.csv`: one clause of a framework, the control that meets it, the check kind and its parameters. | [5.1](../doc/spec.md#51-governancerequirementscsv) |
| check | One SQL query generated from a contract rule or a requirement row, of one of eight kinds. Severity `block` stops the build, `flag` is recorded. | [5.2](../doc/spec.md#52-check-kinds) |
| evidence | `gold/evidence`: one row per check per run, append-only. It names the dataset version, the result, the engine and the commit. | [5.3](../doc/spec.md#53-goldevidence) |
| dataset_version | The sha256 of the sorted list of Parquet file digests in a dataset. Identical files give an identical version. | [5.3](../doc/spec.md#53-goldevidence) |
| ALCOA+ | Data integrity principles: attributable, legible, contemporaneous, original, accurate, plus complete, consistent, enduring, available. One of the frameworks of the requirements table. | [3.1](../doc/spec.md#31-bronze), [5.1](../doc/spec.md#51-governancerequirementscsv) |
| Part 11 | US FDA rule 21 CFR Part 11 on electronic records and signatures. Framework `Part11` in the requirements table. | [5.1](../doc/spec.md#51-governancerequirementscsv) |
| DuckDB-WASM | DuckDB compiled to WebAssembly. The page loads it from a pinned CDN version and reruns the checks in the browser. | [8](../doc/spec.md#8-browser-page) |
