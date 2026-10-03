# Benchmarks

## Setup

Read by `pipeline/bench_doc.py` when this file was written.

| setting | value |
|---|---|
| CPU count | 12 |
| RAM | 15,544.64 MiB |
| Python | 3.14.4 |
| DuckDB Python | 1.5.5 |
| DuckDB CLI | v2.0.0-alpha42839 (Cyanoptera) 31adc8b766 |
| git commit | 7595807e310f66b01f12d5a81980487a8b70b537 |
| Network location | https://mrbisonte.github.io/ecog-lakehouse/data |

## Build

Counts of the build in `DATA_DIR`, built at commit `5cec32a1a8bce3b9c5d1101894a2ccd25cb94835` with DuckDB 1.5.5. Canary subjects are left out. Bytes are the recording Parquet files of each layer.

| experiment | subjects | runs | channels | samples | bronze_bytes | silver_bytes |
|---|---|---|---|---|---|---|
| faces_basic | 14 | 14 | 714 | 189,253,080 | 1,297.11 MiB | 1,973.40 MiB |
| fingerflex | 9 | 9 | 484 | 258,340,520 | 1,637.66 MiB | 2,563.62 MiB |
| motor_basic | 19 | 19 | 1,043 | 412,046,520 | 2,704.42 MiB | 4,116.54 MiB |

Files ingested: 45. Build wall clock, first ingestion to the end of the first evidence run: 355.59 seconds.

## Fault A: single row group, unpartitioned, unsorted

DuckDB CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`. Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, the smallest non canary one, over `https://mrbisonte.github.io/ecog-lakehouse/data`, every file of the layout in one read_parquet. Aggregate: `SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1`. One record: `SELECT avg(value_uv), count(*) FROM read_parquet([URLS]) WHERE lid = '01a0c53a-e0f9-2030-000c-105000000000'`, the middle record of 40. Seconds are min / median / max of three CLI runs each; GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE.

| layout | files | row groups | size | sorted by lid, sample_idx | aggregate, read_ahead_depth = 0, s min / median / max | aggregate, default, s min / median / max | aggregate GETs | aggregate received | one record, s min / median / max | one record GETs | one record received |
|---|---|---|---|---|---|---|---|---|---|---|---|
| before, one row group | 1 | 1 | 49.55 MiB | true | 1.47 / 2.53 / 3.62 | 0.94 / 1.11 / 1.58 | 11 | 21.5 MiB | 0.96 / 1.00 / 2.07 | 10 | 19.5 MiB |
| after, partitioned and sorted | 2 | 38 | 72.74 MiB | true | 2.78 / 3.07 / 7.47 | 2.41 / 2.64 / 2.98 | 38 | 72.7 MiB | 0.57 / 0.58 / 0.62 | 5 | 6.7 MiB |

## Fault D: synchronous one-file-at-a-time loop

10 Parquet files from `docs/data/manifest.json` over `https://mrbisonte.github.io/ecog-lakehouse/data`. Before: `faults/d/plant.py`, urllib, one file after another into a temp directory, then count. After: `faults/d/fix.sql`, one `read_parquet` over the URL list, then `faults/d/verify.sql`, every file read once more in full with read_blob and its sha256 compared with the manifest, the integrity check that replaces the CDN's ETag. Seconds are wall clock of one run each; the digest check downloads every byte, so it is timed apart.

| approach | rows | seconds | digest check seconds | files hashed | digest mismatches |
|---|---|---|---|---|---|
| before, sequential download then count | 15,337,108 | 6.31 | | 0 | not checked |
| after, one httpfs statement, then verify.sql | 15,337,108 | 0.33 | 5.63 | 10 | 0 |

## Fault F: flaky remote reads without retries

`faults/f/flaky_proxy.py` in front of `https://mrbisonte.github.io/ecog-lakehouse/data`, 503 on a fraction 0.1 of range requests, deterministic. Query: the Fault A aggregate, one range request per row group, over `faults/a/good/experiment=faces_basic/subject_pid=72d88db77f3716bb/data_0.parquet`. Ten attempts per row, each timed. The first two rows run on DuckDB 1.5.5, the pipeline's engine; the third on the CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`, which retries a 503 on its own whatever http_retries says.

| engine, setting | successes | mean seconds |
|---|---|---|
| before, 1.5.5, http_retries = 0 | 0/10 | 1.56 |
| after, 1.5.5, http_retries = 8, wait 50 ms, backoff 2 | 10/10 | 1.87 |
| 2.0 alpha CLI, http_retries = 0 | 10/10 | 2.65 |

## Fault G: pathological generated SQL

`faults/g/plant.py` wrote three predicates over 512 channels under `docs/data/faults/g`. Seconds are wall clock of `EXPLAIN` in the CLI, parse and bind, no rows read. The generator in `pipeline/checks.py` emits the IN form and refuses the other two (test `test_generator_rejects_malformed_and_deeply_nested_sql`).

| predicate | nesting | EXPLAIN seconds |
|---|---|---|
| before, one OR per channel, nested | 512 | 0.09 |
| after, channel_idx IN (...) | 1 | 0.04 |

Malformed variant, one parenthesis short, as the parser reports it:

```
    Parser Error: syntax error at or near "511"
    LINE 1: ...) OR channel_idx = 509) OR channel_idx = 510) OR channel_idx = 511
                                                                              ^^^
```

## Fault A sweep: row group size against requests and bytes

DuckDB CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766` and DuckDB `1.5.5` through Python. Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, sorted by `lid, sample_idx`, written as one file per row group size and served by `faults/serve.py` on `http://127.0.0.1:8765`. Query: `SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1`, over one file. GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE. Seconds are min / median / max of three CLI runs on loopback, not evidence of a network. Written by `faults/a/sweep.sh`, not by make bench.

| rows per row group | row groups | size | engine | setting | GETs | received | s min / median / max |
|---|---|---|---|---|---|---|---|
| 198,656 | 37 | 72.65 MiB | cli | default | 37 | 72.6 MiB | 1.29 / 1.51 / 2.10 |
| 198,656 | 37 | 72.65 MiB | cli | SET enable_external_file_cache = false; | 75 | 16.1 MiB | 1.91 / 2.20 / 3.74 |
| 198,656 | 37 | 72.65 MiB | cli | SET external_file_cache_remote_block_size = 262144; | 188 | 46.8 MiB | 1.91 / 3.32 / 5.98 |
| 198,656 | 37 | 72.65 MiB | python | default | 75 | 16.1 MiB | not timed |
| 393,216 | 19 | 71.32 MiB | cli | default | 36 | 71.3 MiB | 1.50 / 1.51 / 1.91 |
| 393,216 | 19 | 71.32 MiB | cli | SET enable_external_file_cache = false; | 39 | 15.2 MiB | 1.66 / 1.66 / 1.72 |
| 393,216 | 19 | 71.32 MiB | cli | SET external_file_cache_remote_block_size = 262144; | 102 | 25.3 MiB | 1.59 / 1.59 / 2.17 |
| 393,216 | 19 | 71.32 MiB | python | default | 39 | 15.2 MiB | not timed |
| 786,432 | 10 | 71.13 MiB | cli | default | 27 | 53.1 MiB | 1.50 / 1.50 / 2.10 |
| 786,432 | 10 | 71.13 MiB | cli | SET enable_external_file_cache = false; | 21 | 15.4 MiB | 1.26 / 1.28 / 1.28 |
| 786,432 | 10 | 71.13 MiB | cli | SET external_file_cache_remote_block_size = 262144; | 81 | 20.1 MiB | 1.59 / 2.10 / 2.31 |
| 786,432 | 10 | 71.13 MiB | python | default | 21 | 15.4 MiB | not timed |
| 1,048,576 | 7 | 59.95 MiB | cli | default | 22 | 43.9 MiB | 1.27 / 1.27 / 1.30 |
| 1,048,576 | 7 | 59.95 MiB | cli | SET enable_external_file_cache = false; | 15 | 15.1 MiB | 1.08 / 1.08 / 1.09 |
| 1,048,576 | 7 | 59.95 MiB | cli | SET external_file_cache_remote_block_size = 262144; | 75 | 18.6 MiB | 1.28 / 1.29 / 2.30 |
| 1,048,576 | 7 | 59.95 MiB | python | default | 15 | 15.1 MiB | not timed |
| 2,097,152 | 4 | 54.78 MiB | cli | default | 16 | 30.7 MiB | 1.07 / 1.08 / 1.08 |
| 2,097,152 | 4 | 54.78 MiB | cli | SET enable_external_file_cache = false; | 9 | 15.6 MiB | 0.06 / 1.07 / 1.09 |
| 2,097,152 | 4 | 54.78 MiB | cli | SET external_file_cache_remote_block_size = 262144; | 73 | 18.0 MiB | 1.53 / 2.10 / 2.11 |
| 2,097,152 | 4 | 54.78 MiB | python | default | 9 | 15.6 MiB | not timed |
| 4,194,304 | 2 | 50.81 MiB | cli | default | 14 | 26.8 MiB | 1.08 / 1.08 / 1.08 |
| 4,194,304 | 2 | 50.81 MiB | cli | SET enable_external_file_cache = false; | 5 | 15.6 MiB | 0.07 / 0.07 / 0.08 |
| 4,194,304 | 2 | 50.81 MiB | cli | SET external_file_cache_remote_block_size = 262144; | 67 | 16.5 MiB | 1.50 / 1.51 / 2.34 |
| 4,194,304 | 2 | 50.81 MiB | python | default | 5 | 15.6 MiB | not timed |
| one row group | 1 | 49.55 MiB | cli | default | 11 | 21.5 MiB | 1.11 / 1.11 / 1.11 |
| one row group | 1 | 49.55 MiB | cli | SET enable_external_file_cache = false; | 3 | 16.3 MiB | 0.09 / 0.09 / 0.10 |
| one row group | 1 | 49.55 MiB | cli | SET external_file_cache_remote_block_size = 262144; | 70 | 17.3 MiB | 1.53 / 1.63 / 2.13 |
| one row group | 1 | 49.55 MiB | python | default | 3 | 16.3 MiB | not timed |

## Fault A encodings: delta and zstd against the lost dictionary

Issue 29, measured by `faults/a/encodings.sh`. DuckDB Python v1.5.5, the pipeline's engine, reads the Parquet metadata and writes the variants; the CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766` reads them too and runs the queries over HTTP.

`silver/recording` in DATA_DIR as the pipeline wrote it, 45 files, 4,408 row groups, 871,159,620 rows, from parquet_metadata. A row group keeps a dictionary when its column chunk has a dictionary page.

| column | encodings | row groups with a dictionary | compressed bytes | uncompressed bytes | compressed bytes per value | share of compressed bytes, percent |
|---|---|---|---|---|---|---|
| sample_idx | PLAIN | 0 of 4,408 | 3,484,958,980 | 3,484,775,124 | 4.00 | 39.0 |
| ts_ms | PLAIN | 0 of 4,408 | 3,484,958,980 | 3,484,775,124 | 4.00 | 39.0 |
| value_uv | PLAIN, PLAIN_DICTIONARY | 4,154 of 4,408 | 1,969,591,200 | 1,969,569,507 | 2.26 | 22.0 |
| lid | PLAIN_DICTIONARY | 4,408 of 4,408 | 315,482 | 316,512 | 0.00 | 0.0 |
| subject_pid | PLAIN_DICTIONARY | 4,408 of 4,408 | 304,149 | 286,517 | 0.00 | 0.0 |
| experiment | PLAIN_DICTIONARY | 4,408 of 4,408 | 280,783 | 263,151 | 0.00 | 0.0 |
| channel_idx | PLAIN_DICTIONARY | 4,408 of 4,408 | 252,535 | 234,903 | 0.00 | 0.0 |
| run | PLAIN_DICTIONARY | 4,408 of 4,408 | 233,621 | 215,989 | 0.00 | 0.0 |

Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, the smallest non canary one, 1 file, 37 row groups, 7,236,800 rows in Silver, written once per variant into one file under ENCODINGS_DIR by `DuckDB version v1.5.5 (build d8cdaa33fd)`, sorted by lid, sample_idx, row groups of 198,656 rows, the columns of `faults/a/fix.sql`'s output. Variant names are Parquet writer version and compression; v1 snappy is today's. `same` means the row count and sum match v1 snappy read by DuckDB Python, 7,236,800 rows, sum(value_uv) -1873984.021144.

| variant | file bytes | row groups | ts_ms bytes | sample_idx bytes | value_uv bytes | ts_ms encodings | sample_idx encodings | value_uv encodings | DuckDB Python read | CLI read |
|---|---|---|---|---|---|---|---|---|---|---|
| v1 snappy | 76,155,922 | 37 | 28,949,874 | 28,949,874 | 16,814,334 | PLAIN | PLAIN | PLAIN_DICTIONARY | same | same |
| v2 snappy | 18,281,020 | 37 | 12,542 | 12,542 | 16,814,334 | DELTA_BINARY_PACKED | DELTA_BINARY_PACKED | RLE_DICTIONARY | same | same |
| v1 zstd | 52,958,402 | 37 | 17,462,325 | 17,462,325 | 16,590,195 | PLAIN | PLAIN | PLAIN_DICTIONARY | same | same |
| v2 zstd | 18,040,532 | 37 | 3,508 | 3,508 | 16,590,195 | DELTA_BINARY_PACKED | DELTA_BINARY_PACKED | RLE_DICTIONARY | same | same |

The same files over `http://127.0.0.1:8765`, `faults/serve.py` on loopback, with the CLI. Aggregate: `SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1`. One record: `SELECT avg(value_uv), count(*) FROM read_parquet([URLS]) WHERE lid = '01a0d595-33ba-2030-000c-105000000000'`, the middle record of 40. Seconds are min / median / max of three CLI runs each; GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE.

| variant | aggregate GETs | aggregate received | aggregate, s min / median / max | one record GETs | one record received | one record, s min / median / max |
|---|---|---|---|---|---|---|
| v1 snappy | 37 | 72.6 MiB | 1.50 / 2.11 / 2.11 | 5 | 8.6 MiB | 0.05 / 0.05 / 0.06 |
| v2 snappy | 9 | 17.4 MiB | 0.06 / 0.06 / 0.06 | 3 | 5.4 MiB | 0.05 / 0.05 / 0.05 |
| v1 zstd | 26 | 50.5 MiB | 0.07 / 1.08 / 1.08 | 4 | 6.5 MiB | 0.05 / 0.05 / 0.05 |
| v2 zstd | 9 | 17.2 MiB | 0.05 / 0.05 / 0.06 | 3 | 5.2 MiB | 0.05 / 0.05 / 0.05 |
