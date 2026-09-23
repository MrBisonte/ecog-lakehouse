-- Fault A plant, spec 6: one subject of silver/recording as one file, one row group, no
-- partition columns in the path. FAULT_EXPERIMENT and FAULT_SUBJECT are the smallest non canary
-- partition, chosen by bench.sh through the pipeline's own connection, so the file stays
-- under the 95 MB publishing limit. Run from the repo root with the DuckDB CLI.
COPY (
    SELECT *
    FROM read_parquet(
        getenv('DATA_DIR') || '/silver/recording/experiment=' || getenv('FAULT_EXPERIMENT')
            || '/subject_pid=' || getenv('FAULT_SUBJECT') || '/*.parquet',
        hive_partitioning = true, hive_types_autocast = false)
) TO 'docs/data/faults/a/bad/recording.parquet' (FORMAT parquet, ROW_GROUP_SIZE 100000000);
