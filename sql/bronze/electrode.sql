-- bronze/electrode, spec 3.1. One row per channel, NULL where the file has no location.
COPY (
    SELECT
        '{{experiment}}' AS experiment,
        '{{subject_src}}' AS subject_src,
        channel_idx::SMALLINT AS channel_idx,
        x_mm::FLOAT AS x_mm,
        y_mm::FLOAT AS y_mm,
        z_mm::FLOAT AS z_mm,
        brain_area::VARCHAR AS brain_area,
        '{{ingest_id}}' AS ingest_id,
        lid_encode(epoch_ms(TIMESTAMP '{{ingested_at}}'), 1, {{experiment_code}},
                   {{ingest_ord}}, {{run}}, channel_idx, 0) AS lid
    FROM src_electrode
) TO '{{data_dir}}/bronze/electrode'
(FORMAT parquet, PARTITION_BY (experiment, subject_src), WRITE_PARTITION_COLUMNS, APPEND);
