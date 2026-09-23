# bench.md

Counts of the build in `DATA_DIR`, written by `pipeline/bench_doc.py` at commit `5ed73af47fbd41c05ab0e11db102b74d27c35331` with DuckDB 1.5.5. Canary subjects are left out. Bytes are the recording Parquet files of each layer.

| experiment | subjects | runs | channels | samples | bronze_bytes | silver_bytes |
|---|---|---|---|---|---|---|
| faces_basic | 14 | 14 | 714 | 189253080 | 1360689759 | 2069260676 |
| fingerflex | 9 | 9 | 484 | 258340520 | 1717261283 | 2688152076 |
| motor_basic | 19 | 19 | 1043 | 412046520 | 2835059858 | 4316499632 |

Files ingested: 45. Build wall clock, first ingestion to last evidence row: 0:06:07.136034.

## Fault A: single row group, unpartitioned, unsorted

DuckDB CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`. Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, the smallest non canary one. Query: `SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet('URL') GROUP BY 1` over `http://127.0.0.1:8765`. Seconds are the median of three CLI runs each.

| layout | row groups | bytes | sorted by lid, sample_idx | read_ahead_depth = 0 | default |
|---|---|---|---|---|---|
| before, one row group | 1 | 51960395 | true | 1.144 | 1.124 |
| after, partitioned and sorted | 29 | 59093173 | true | 1.084 | 1.312 |

## Fault D: synchronous one-file-at-a-time loop

5 Parquet files from `docs/data/manifest.json` over `http://127.0.0.1:8765`. Before: `faults/d/plant.py`, urllib, one file after another into a temp directory, then count. After: `faults/d/fix.sql`, one `read_parquet` over the URL list. Seconds are wall clock of one run each.

| approach | rows | seconds |
|---|---|---|
| before, sequential download then count | 863287 | 0.174 |
| after, one httpfs statement | 863287 | 0.056 |

## Fault F: flaky remote reads without retries

`faults/f/flaky_proxy.py` in front of `http://127.0.0.1:8765`, 503 on a fraction 0.1 of range requests, deterministic. Query: the Fault A aggregate, one range request per row group, over `faults/a/good/experiment=faces_basic/subject_pid=72d88db77f3716bb/data_0.parquet`. Ten attempts per row, each timed. The first two rows run on DuckDB 1.5.5, the pipeline's engine; the third on the CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`, which retries a 503 on its own whatever http_retries says.

| engine, setting | successes | mean seconds |
|---|---|---|
| before, 1.5.5, http_retries = 0 | 0/10 | 1.048 |
| after, 1.5.5, http_retries = 8, wait 50 ms, backoff 2 | 10/10 | 1.055 |
| 2.0 alpha CLI, http_retries = 0 | 10/10 | 1.554 |

## Fault G: pathological generated SQL

`faults/g/plant.py` wrote three predicates over 512 channels under `docs/data/faults/g`. Seconds are wall clock of `EXPLAIN` in the CLI, parse and bind, no rows read. The generator in `pipeline/checks.py` emits the IN form and refuses the other two (test `test_generator_rejects_malformed_and_deeply_nested_sql`).

| predicate | nesting | EXPLAIN seconds |
|---|---|---|
| before, one OR per channel, nested | 512 | 0.080 |
| after, channel_idx IN (...) | 1 | 0.041 |

Malformed variant, one parenthesis short, as the parser reports it:

```
    Parser Error: syntax error at or near "511"
    LINE 1: ...) OR channel_idx = 509) OR channel_idx = 510) OR channel_idx = 511
                                                                              ^^^
```

## Fault A: single row group, unpartitioned, unsorted

DuckDB CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`. Subject partition `experiment=faces_basic/subject_pid=72d88db77f3716bb`, the smallest non canary one. Query: `SET unsafe_disable_etag_checks = true; SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet([URLS]) GROUP BY 1` over `https://mrbisonte.github.io/ibrain/data`, every file of the layout in one read_parquet. Seconds are the median of three CLI runs each.

| layout | files | row groups | bytes | sorted by lid, sample_idx | read_ahead_depth = 0 | default |
|---|---|---|---|---|---|---|
| before, one row group | 1 | 1 | 51960395 | true | 1.041 | 1.076 |
| after, partitioned and sorted | 2 | 38 | 76269314 | true | 2.744 | 2.827 |

## Fault D: synchronous one-file-at-a-time loop

8 Parquet files from `docs/data/manifest.json` over `https://mrbisonte.github.io/ibrain/data`. Before: `faults/d/plant.py`, urllib, one file after another into a temp directory, then count. After: `faults/d/fix.sql`, one `read_parquet` over the URL list. Seconds are wall clock of one run each.

| approach | rows | seconds |
|---|---|---|
| before, sequential download then count | 15336887 | 5.102 |
| after, one httpfs statement | 15336887 | 0.325 |

## Fault F: flaky remote reads without retries

`faults/f/flaky_proxy.py` in front of `https://mrbisonte.github.io/ibrain/data`, 503 on a fraction 0.1 of range requests, deterministic. Query: the Fault A aggregate, one range request per row group, over `faults/a/good/experiment=faces_basic/subject_pid=72d88db77f3716bb/data_0.parquet`. Ten attempts per row, each timed. The first two rows run on DuckDB 1.5.5, the pipeline's engine; the third on the CLI `v2.0.0-alpha42839 (Cyanoptera) 31adc8b766`, which retries a 503 on its own whatever http_retries says.

| engine, setting | successes | mean seconds |
|---|---|---|
| before, 1.5.5, http_retries = 0 | 0/10 | 1.472 |
| after, 1.5.5, http_retries = 8, wait 50 ms, backoff 2 | 10/10 | 1.485 |
| 2.0 alpha CLI, http_retries = 0 | 10/10 | 4.727 |

## Fault G: pathological generated SQL

`faults/g/plant.py` wrote three predicates over 512 channels under `docs/data/faults/g`. Seconds are wall clock of `EXPLAIN` in the CLI, parse and bind, no rows read. The generator in `pipeline/checks.py` emits the IN form and refuses the other two (test `test_generator_rejects_malformed_and_deeply_nested_sql`).

| predicate | nesting | EXPLAIN seconds |
|---|---|---|
| before, one OR per channel, nested | 512 | 0.094 |
| after, channel_idx IN (...) | 1 | 0.047 |

Malformed variant, one parenthesis short, as the parser reports it:

```
    Parser Error: syntax error at or near "511"
    LINE 1: ...) OR channel_idx = 509) OR channel_idx = 510) OR channel_idx = 511
                                                                              ^^^
```
