-- silver/electrode, spec 3.2: Bronze with subject_src replaced by subject_pid, ingest_id removed.
COPY (
    SELECT
        b.experiment,
        k.subject_pid,
        b.channel_idx,
        b.x_mm,
        b.y_mm,
        b.z_mm,
        b.brain_area,
        lid_relayer(b.lid, 1) AS lid
    FROM bronze_electrode b
    JOIN keyring.key_map k USING (subject_src)
    ORDER BY lid
) TO '{{data_dir}}/silver/electrode'
(FORMAT parquet, PARTITION_BY (experiment, subject_pid), WRITE_PARTITION_COLUMNS, OVERWRITE);
