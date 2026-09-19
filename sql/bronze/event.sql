-- bronze/event, spec 3.1. One row per cue onset. Events belong to the run, not to a channel,
-- so their lid carries channel 0.
COPY (
    SELECT
        '{{experiment}}' AS experiment,
        '{{subject_src}}' AS subject_src,
        {{run}}::SMALLINT AS run,
        e.sample_idx::INTEGER AS sample_idx,
        e.event_code::SMALLINT AS event_code,
        l.event_label::VARCHAR AS event_label,
        '{{ingest_id}}' AS ingest_id,
        lid_encode(epoch_ms(TIMESTAMP '{{ingested_at}}'), 1, {{experiment_code}},
                   {{ingest_ord}}, {{run}}, 0, 0) AS lid
    FROM src_event e
    LEFT JOIN src_label l USING (event_code)
) TO '{{data_dir}}/bronze/event'
(FORMAT parquet, PARTITION_BY (experiment, subject_src), WRITE_PARTITION_COLUMNS, APPEND);
