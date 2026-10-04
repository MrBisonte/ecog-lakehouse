# Benchmarks

## Setup

Read by `pipeline/bench_doc.py` when this file was written.

| setting | value |
|---|---|
| CPU count | 12 |
| RAM | 15,544.63 MiB |
| Python | 3.14.4 |
| DuckDB Python | 1.5.5 |
| DuckDB CLI | v2.0.0-alpha43763 (Cyanoptera) 96063b9e39 |
| DuckDB CLI sha256 | 8e3d17e36ebfb868c020787f60dffe2457f3b43ab7013adf40e9cb2c1be449e8 |
| git commit | 192f7b8f0c161592dbab219314fabe4e0fe199e1 |
| Network location | https://mrbisonte.github.io/ecog-lakehouse/data |

## Build

Counts of the build in `DATA_DIR`, built at commit `3461dd85f151009d065ceb5e7997f7e33f0ddfd5` with DuckDB 1.5.5. Canary subjects are left out. Bytes are the recording Parquet files of each layer.

| experiment | subjects | runs | channels | samples | bronze_bytes | silver_bytes |
|---|---|---|---|---|---|---|
| faces_basic | 14 | 14 | 714 | 189,253,080 | 1,297.11 MiB | 478.15 MiB |
| fingerflex | 9 | 9 | 484 | 258,340,520 | 1,637.66 MiB | 561.70 MiB |
| motor_basic | 19 | 19 | 1,043 | 412,046,520 | 2,704.42 MiB | 939.36 MiB |

Files ingested: 45. Build wall clock, first ingestion to the end of the first evidence run: 355.59 seconds.

## Fault A: single row group, unpartitioned, unsorted

DuckDB CLI `v2.0.0-alpha43763 (Cyanoptera) 96063b9e39`. Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, the smallest non canary one, over `https://mrbisonte.github.io/ecog-lakehouse/data`, every file of the layout in one read_parquet. Aggregate: `SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1`. One record: `SELECT avg(value_uv), count(*) FROM read_parquet([URLS]) WHERE lid = '01a0d595-33ba-2030-000c-105000000000'`, the middle record of 40. Seconds are min / median / max of three CLI runs each; GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE.

| layout | files | row groups | size | sorted by lid, sample_idx | aggregate, read_ahead_depth = 0, s min / median / max | aggregate, default, s min / median / max | aggregate GETs | aggregate received | one record, s min / median / max | one record GETs | one record received |
|---|---|---|---|---|---|---|---|---|---|---|---|
| before, one row group | 1 | 1 | 49.55 MiB | true | 1.02 / 1.47 / 3.37 | 1.01 / 1.43 / 1.59 | 11 | 16.3 MiB | 0.97 / 1.05 / 1.07 | 11 | 16.3 MiB |
| after, partitioned and sorted | 2 | 37 | 17.45 MiB | true | 0.92 / 1.20 / 2.65 | 0.99 / 1.00 / 1.21 | 39 | 16.1 MiB | 0.37 / 0.38 / 0.39 | 5 | 487.8 KiB |

## Fault D: synchronous one-file-at-a-time loop

11 Parquet files from `docs/data/manifest.json` over `https://mrbisonte.github.io/ecog-lakehouse/data`. Before: `faults/d/plant.py`, urllib, one file after another into a temp directory, then count. After: `faults/d/fix.sql`, one `read_parquet` over the URL list, then `faults/d/verify.sql`, every file read once more in full with read_blob and its sha256 compared with the manifest, the integrity check that replaces the CDN's ETag. Seconds are wall clock of one run each; the digest check downloads every byte, so it is timed apart.

| approach | rows | seconds | digest check seconds | files hashed | digest mismatches |
|---|---|---|---|---|---|
| before, sequential download then count | 15,337,219 | 6.60 | | 0 | not checked |
| after, one httpfs statement, then verify.sql | 15,337,219 | 0.64 | 5.45 | 11 | 0 |

## Fault F: flaky remote reads without retries

`faults/f/flaky_proxy.py` in front of `https://mrbisonte.github.io/ecog-lakehouse/data`, 503 on a fraction 0.1 of range requests, deterministic. Query: the Fault A aggregate, one range request per row group, over `faults/a/good/experiment=faces_basic/subject_pid=72d88db77f3716bb/data_0.parquet`. Ten attempts per row, each timed. The first two rows run on DuckDB 1.5.5, the pipeline's engine; the third on the CLI `v2.0.0-alpha43763 (Cyanoptera) 96063b9e39`, which retries a 503 on its own whatever http_retries says.

| engine, setting | successes | mean seconds |
|---|---|---|
| before, 1.5.5, http_retries = 0 | 0/10 | 5.97 |
| after, 1.5.5, http_retries = 8, wait 50 ms, backoff 2 | 10/10 | 1.49 |
| 2.0 alpha CLI, http_retries = 0 | 10/10 | 1.94 |

## Fault G: pathological generated SQL

`faults/g/plant.py` wrote three predicates over 512 channels under `docs/data/faults/g`. Seconds are wall clock of `EXPLAIN` in the CLI, parse and bind, no rows read. The generator in `pipeline/checks.py` emits the IN form and refuses the other two (test `test_generator_rejects_malformed_and_deeply_nested_sql`).

| predicate | nesting | EXPLAIN seconds |
|---|---|---|
| before, one OR per channel, nested | 512 | 0.08 |
| after, channel_idx IN (...) | 1 | 0.04 |

Malformed variant, one parenthesis short, as the parser reports it:

```
    Parser Error: syntax error at or near "511"
    LINE 1: ...) OR channel_idx = 509) OR channel_idx = 510) OR channel_idx = 511
                                                                              ^^^
```

## Fault A sweep: row group size against requests and bytes

DuckDB CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`, `v2.0.0-alpha43763 (Cyanoptera) 96063b9e39`, and DuckDB `1.5.5` through Python. Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, sorted by `lid, sample_idx`, written as one file per row group size and served by `faults/serve.py` on `http://127.0.0.1:8765`. Query: `SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1`, over one file. GET requests and bytes received are the HTTP statistics of EXPLAIN ANALYZE, three runs each: one value where the runs agree, all three where they do not. Not timed: loopback seconds say nothing about a network. Written by `faults/a/sweep.sh`, not by make bench.

| rows per row group | row groups | size | engine | setting | GETs | received |
|---|---|---|---|---|---|---|
| 198,656 | 37 | 72.65 MiB | v2.0.0-alpha42839, CLI | default | 37 | 72.6 MiB |
| 198,656 | 37 | 72.65 MiB | v2.0.0-alpha42839, CLI | SET enable_external_file_cache = false; | 75 | 16.1 MiB |
| 198,656 | 37 | 72.65 MiB | v2.0.0-alpha42839, CLI | SET external_file_cache_remote_block_size = 262144; | 139, 186 | 34.6 MiB, 46.3 MiB |
| 198,656 | 37 | 72.65 MiB | v2.0.0-alpha43763, CLI | default | 50, 75 | 34.8 MiB, 16.4 MiB |
| 198,656 | 37 | 72.65 MiB | v2.0.0-alpha43763, CLI | SET enable_external_file_cache = false; | 75, 51 | 16.1 MiB, 33.9 MiB |
| 198,656 | 37 | 72.65 MiB | v2.0.0-alpha43763, CLI | SET external_file_cache_remote_max_block_size = 262144; | 156, 158, 111 | 33.3 MiB, 34.1 MiB, 16.4 MiB |
| 198,656 | 37 | 72.65 MiB | 1.5.5, Python | default | 75 | 16.1 MiB |
| 393,216 | 19 | 71.32 MiB | v2.0.0-alpha42839, CLI | default | 36 | 71.3 MiB |
| 393,216 | 19 | 71.32 MiB | v2.0.0-alpha42839, CLI | SET enable_external_file_cache = false; | 39, 32, 39 | 15.2 MiB, 24.9 MiB, 15.2 MiB |
| 393,216 | 19 | 71.32 MiB | v2.0.0-alpha42839, CLI | SET external_file_cache_remote_block_size = 262144; | 101, 132 | 25.0 MiB, 32.8 MiB |
| 393,216 | 19 | 71.32 MiB | v2.0.0-alpha43763, CLI | default | 38, 39, 38 | 22.0 MiB, 15.4 MiB, 25.0 MiB |
| 393,216 | 19 | 71.32 MiB | v2.0.0-alpha43763, CLI | SET enable_external_file_cache = false; | 39 | 15.2 MiB |
| 393,216 | 19 | 71.32 MiB | v2.0.0-alpha43763, CLI | SET external_file_cache_remote_max_block_size = 262144; | 125, 94 | 25.0 MiB, 15.4 MiB |
| 393,216 | 19 | 71.32 MiB | 1.5.5, Python | default | 39 | 15.2 MiB |
| 786,432 | 10 | 71.13 MiB | v2.0.0-alpha42839, CLI | default | 27 | 53.1 MiB |
| 786,432 | 10 | 71.13 MiB | v2.0.0-alpha42839, CLI | SET enable_external_file_cache = false; | 21 | 15.4 MiB |
| 786,432 | 10 | 71.13 MiB | v2.0.0-alpha42839, CLI | SET external_file_cache_remote_block_size = 262144; | 81 | 20.1 MiB |
| 786,432 | 10 | 71.13 MiB | v2.0.0-alpha43763, CLI | default | 21 | 15.5 MiB |
| 786,432 | 10 | 71.13 MiB | v2.0.0-alpha43763, CLI | SET enable_external_file_cache = false; | 21 | 15.4 MiB |
| 786,432 | 10 | 71.13 MiB | v2.0.0-alpha43763, CLI | SET external_file_cache_remote_max_block_size = 262144; | 76 | 15.5 MiB |
| 786,432 | 10 | 71.13 MiB | 1.5.5, Python | default | 21 | 15.4 MiB |
| 1,048,576 | 7 | 59.95 MiB | v2.0.0-alpha42839, CLI | default | 22 | 43.9 MiB |
| 1,048,576 | 7 | 59.95 MiB | v2.0.0-alpha42839, CLI | SET enable_external_file_cache = false; | 15 | 15.1 MiB |
| 1,048,576 | 7 | 59.95 MiB | v2.0.0-alpha42839, CLI | SET external_file_cache_remote_block_size = 262144; | 75 | 18.6 MiB |
| 1,048,576 | 7 | 59.95 MiB | v2.0.0-alpha43763, CLI | default | 22 | 15.2 MiB |
| 1,048,576 | 7 | 59.95 MiB | v2.0.0-alpha43763, CLI | SET enable_external_file_cache = false; | 15 | 15.1 MiB |
| 1,048,576 | 7 | 59.95 MiB | v2.0.0-alpha43763, CLI | SET external_file_cache_remote_max_block_size = 262144; | 71 | 15.2 MiB |
| 1,048,576 | 7 | 59.95 MiB | 1.5.5, Python | default | 15 | 15.1 MiB |
| 2,097,152 | 4 | 54.78 MiB | v2.0.0-alpha42839, CLI | default | 16 | 30.7 MiB |
| 2,097,152 | 4 | 54.78 MiB | v2.0.0-alpha42839, CLI | SET enable_external_file_cache = false; | 9 | 15.6 MiB |
| 2,097,152 | 4 | 54.78 MiB | v2.0.0-alpha42839, CLI | SET external_file_cache_remote_block_size = 262144; | 73 | 18.0 MiB |
| 2,097,152 | 4 | 54.78 MiB | v2.0.0-alpha43763, CLI | default | 16 | 15.7 MiB |
| 2,097,152 | 4 | 54.78 MiB | v2.0.0-alpha43763, CLI | SET enable_external_file_cache = false; | 9 | 15.6 MiB |
| 2,097,152 | 4 | 54.78 MiB | v2.0.0-alpha43763, CLI | SET external_file_cache_remote_max_block_size = 262144; | 71 | 15.7 MiB |
| 2,097,152 | 4 | 54.78 MiB | 1.5.5, Python | default | 9 | 15.6 MiB |
| 4,194,304 | 2 | 50.81 MiB | v2.0.0-alpha42839, CLI | default | 14 | 26.8 MiB |
| 4,194,304 | 2 | 50.81 MiB | v2.0.0-alpha42839, CLI | SET enable_external_file_cache = false; | 5 | 15.6 MiB |
| 4,194,304 | 2 | 50.81 MiB | v2.0.0-alpha42839, CLI | SET external_file_cache_remote_block_size = 262144; | 67 | 16.5 MiB |
| 4,194,304 | 2 | 50.81 MiB | v2.0.0-alpha43763, CLI | default | 12 | 15.6 MiB |
| 4,194,304 | 2 | 50.81 MiB | v2.0.0-alpha43763, CLI | SET enable_external_file_cache = false; | 5 | 15.6 MiB |
| 4,194,304 | 2 | 50.81 MiB | v2.0.0-alpha43763, CLI | SET external_file_cache_remote_max_block_size = 262144; | 66 | 15.6 MiB |
| 4,194,304 | 2 | 50.81 MiB | 1.5.5, Python | default | 5 | 15.6 MiB |
| one row group | 1 | 49.55 MiB | v2.0.0-alpha42839, CLI | default | 11 | 21.5 MiB |
| one row group | 1 | 49.55 MiB | v2.0.0-alpha42839, CLI | SET enable_external_file_cache = false; | 3 | 16.3 MiB |
| one row group | 1 | 49.55 MiB | v2.0.0-alpha42839, CLI | SET external_file_cache_remote_block_size = 262144; | 70 | 17.3 MiB |
| one row group | 1 | 49.55 MiB | v2.0.0-alpha43763, CLI | default | 11 | 16.3 MiB |
| one row group | 1 | 49.55 MiB | v2.0.0-alpha43763, CLI | SET enable_external_file_cache = false; | 3 | 16.3 MiB |
| one row group | 1 | 49.55 MiB | v2.0.0-alpha43763, CLI | SET external_file_cache_remote_max_block_size = 262144; | 68 | 16.3 MiB |
| one row group | 1 | 49.55 MiB | 1.5.5, Python | default | 3 | 16.3 MiB |

## Fault A encodings: delta and zstd against the lost dictionary

Issue 29, measured by `faults/a/encodings.sh`. DuckDB Python v1.5.5, the pipeline's engine, reads the Parquet metadata and writes the variants; the CLI `v2.0.0-alpha43763 (Cyanoptera) 96063b9e39` reads them too and runs the queries over HTTP.

`silver/recording` in DATA_DIR as the pipeline wrote it, 45 files, 4,408 row groups, 871,159,620 rows, from parquet_metadata. A row group keeps a dictionary when its column chunk has a dictionary page.

| column | encodings | row groups with a dictionary | compressed bytes | uncompressed bytes | compressed bytes per value | share of compressed bytes, percent |
|---|---|---|---|---|---|---|
| value_uv | BYTE_STREAM_SPLIT, RLE_DICTIONARY | 4,154 of 4,408 | 1,939,034,911 | 1,969,569,507 | 2.23 | 99.8 |
| sample_idx | DELTA_BINARY_PACKED | 0 of 4,408 | 992,414 | 15,531,674 | 0.00 | 0.1 |
| ts_ms | DELTA_BINARY_PACKED | 0 of 4,408 | 992,414 | 15,531,674 | 0.00 | 0.1 |
| lid | RLE_DICTIONARY | 4,408 of 4,408 | 315,482 | 316,512 | 0.00 | 0.0 |
| subject_pid | RLE_DICTIONARY | 4,408 of 4,408 | 304,149 | 286,517 | 0.00 | 0.0 |
| experiment | RLE_DICTIONARY | 4,408 of 4,408 | 280,783 | 263,151 | 0.00 | 0.0 |
| channel_idx | RLE_DICTIONARY | 4,408 of 4,408 | 252,535 | 234,903 | 0.00 | 0.0 |
| run | RLE_DICTIONARY | 4,408 of 4,408 | 233,621 | 215,989 | 0.00 | 0.0 |

Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, the smallest non canary one, 1 file, 37 row groups, 7,236,800 rows in Silver, written once per variant into one file under ENCODINGS_DIR by `DuckDB version v1.5.5 (build d8cdaa33fd)`, sorted by lid, sample_idx, row groups of 198,656 rows, the columns of `faults/a/fix.sql`'s output. Variant names are Parquet writer version and compression; v2 snappy is what Silver holds since ADR-0007, v1 snappy what it held before. `same` means the row count and sum match v1 snappy read by DuckDB Python, 7,236,800 rows, sum(value_uv) -1873984.021144.

| variant | file bytes | row groups | ts_ms bytes | sample_idx bytes | value_uv bytes | ts_ms encodings | sample_idx encodings | value_uv encodings | DuckDB Python read | CLI read |
|---|---|---|---|---|---|---|---|---|---|---|
| v1 snappy | 76,155,922 | 37 | 28,949,874 | 28,949,874 | 16,814,334 | PLAIN | PLAIN | PLAIN_DICTIONARY | same | same |
| v2 snappy | 18,281,020 | 37 | 12,542 | 12,542 | 16,814,334 | DELTA_BINARY_PACKED | DELTA_BINARY_PACKED | RLE_DICTIONARY | same | same |
| v1 zstd | 52,958,402 | 37 | 17,462,325 | 17,462,325 | 16,590,195 | PLAIN | PLAIN | PLAIN_DICTIONARY | same | same |
| v2 zstd | 18,040,532 | 37 | 3,508 | 3,508 | 16,590,195 | DELTA_BINARY_PACKED | DELTA_BINARY_PACKED | RLE_DICTIONARY | same | same |

The same files over `http://127.0.0.1:8765`, `faults/serve.py` on loopback, with the CLI. Aggregate: `SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1`. One record: `SELECT avg(value_uv), count(*) FROM read_parquet([URLS]) WHERE lid = '01a0d595-33ba-2030-000c-105000000000'`, the middle record of 40. Seconds are min / median / max of three CLI runs each; GET requests and bytes received are one run's HTTP statistics from EXPLAIN ANALYZE.

| variant | aggregate GETs | aggregate received | aggregate, s min / median / max | one record GETs | one record received | one record, s min / median / max |
|---|---|---|---|---|---|---|
| v1 snappy | 56 | 30.3 MiB | 1.50 / 1.51 / 2.13 | 5 | 1019.0 KiB | 0.05 / 0.05 / 0.05 |
| v2 snappy | 38 | 16.0 MiB | 1.49 / 1.51 / 2.10 | 5 | 920.5 KiB | 0.05 / 0.05 / 0.05 |
| v1 zstd | 75 | 16.1 MiB | 1.29 / 1.48 / 2.20 | 5 | 941.1 KiB | 0.05 / 0.05 / 0.05 |
| v2 zstd | 38 | 15.8 MiB | 1.09 / 1.92 / 2.11 | 5 | 909.7 KiB | 0.05 / 0.05 / 0.05 |
