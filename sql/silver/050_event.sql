-- silver/event, spec 3.2: Bronze with subject_pid for subject_src, ts_ms for sample_idx,
-- ingest_id removed.
COPY (
    SELECT
        b.experiment,
        k.subject_pid,
        b.run,
        (b.sample_idx::BIGINT * 1000 / a.sample_rate_hz)::INTEGER AS ts_ms,
        b.event_code,
        b.event_label,
        lid_to_uuid(lid_relayer(lid_from_uuid(b.lid), 1)) AS lid
    FROM bronze_event b
    JOIN keyring.key_map k USING (subject_src)
    JOIN bronze_ingest_audit a USING (ingest_id)
    ORDER BY lid, ts_ms
) TO '{{data_dir}}/silver/event'
(FORMAT parquet, PARTITION_BY (experiment, subject_pid), WRITE_PARTITION_COLUMNS, OVERWRITE);
