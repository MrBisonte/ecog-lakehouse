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
