-- silver/record, spec 12.2. One row per record (file, run, channel), the lineage dimension
-- of Silver. The lid is the Bronze lid with the layer set to 2. n_samples_src counts source
-- samples including NaN, so Gold derives missing_samples from Silver alone.
COPY (
    SELECT
        lid_from_u128(lid_u128(r.lid) + (1::UHUGEINT << 76)) AS lid,
        r.experiment,
        k.subject_pid,
        r.run,
        r.channel_idx,
        count(*)::BIGINT AS n_samples_src
    FROM bronze_recording r
    JOIN keyring.key_map k USING (subject_src)
    GROUP BY ALL
    ORDER BY 1
) TO '{{data_dir}}/silver/record/data_0.parquet' (FORMAT parquet);
