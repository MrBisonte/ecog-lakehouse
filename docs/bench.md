# bench.md

Counts of the build in `DATA_DIR`, written by `pipeline/bench_doc.py` at commit `5ed73af47fbd41c05ab0e11db102b74d27c35331` with DuckDB 1.5.5. Canary subjects are left out. Bytes are the recording Parquet files of each layer.

| experiment | subjects | runs | channels | samples | bronze_bytes | silver_bytes |
|---|---|---|---|---|---|---|
| faces_basic | 14 | 14 | 714 | 189253080 | 1360689759 | 2069260676 |
| fingerflex | 9 | 9 | 484 | 258340520 | 1717261283 | 2688152076 |
| motor_basic | 19 | 19 | 1043 | 412046520 | 2835059858 | 4316499632 |

Files ingested: 45. Build wall clock, first ingestion to last evidence row: 0:06:07.136034.
