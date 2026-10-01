-- bronze/recording, spec 3.1. One row per sample, raw units. A source NaN
-- arrives as NULL: DuckDB reads NaN from the numpy array as NULL. The row is kept.
-- The lid is computed once per record (channel) and joined, not once per sample.
COPY (
    SELECT
        '{{experiment}}' AS experiment,
        '{{subject_src}}' AS subject_src,
        {{run}}::SMALLINT AS run,
        r.channel_idx::SMALLINT AS channel_idx,
        r.sample_idx::INTEGER AS sample_idx,
        r.value_raw::FLOAT AS value_raw,
        '{{ingest_id}}' AS ingest_id,
        l.lid
    FROM src_recording r
    JOIN (
        SELECT
            channel_idx,
            lid_to_uuid(lid_encode(epoch_ms(TIMESTAMP '{{ingested_at}}'), 1, {{experiment_code}},
                                {{ingest_ord}}, {{run}}, channel_idx, 0, {{radioactive}})) AS lid
        FROM (SELECT DISTINCT channel_idx FROM src_recording)
    ) l USING (channel_idx)
) TO '{{data_dir}}/bronze/recording'
(FORMAT parquet, PARTITION_BY (experiment, subject_src, ingest_id), WRITE_PARTITION_COLUMNS, APPEND);
