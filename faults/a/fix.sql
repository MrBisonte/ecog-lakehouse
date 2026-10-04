-- Fault A fix, spec 6, DuckDB v2.0 syntax: partitioned, sorted inside each file, row groups of
-- 198,656 rows (DuckDB rounds the size up to a multiple of 2048; this is the largest value
-- under the 200,000 limit of the partition_layout check). Same subject as plant.sql.
-- The pipeline itself writes this layout with one plain COPY per partition, the v1.x form.
-- Parquet version 2 as in Silver, ADR-0007.
COPY (
    SELECT *
    FROM read_parquet(
        getenv('DATA_DIR') || '/silver/recording/experiment=' || getenv('FAULT_EXPERIMENT')
            || '/subject_pid=' || getenv('FAULT_SUBJECT') || '/*.parquet',
        hive_partitioning = true, hive_types_autocast = false)
) TO 'docs/data/faults/a/good'
(
    FORMAT parquet,
    PARQUET_VERSION v2,
    PARTITION_BY (experiment, subject_pid),
    ORDER BY (lid, sample_idx),
    ROW_GROUP_SIZE 198656
);
