-- silver/record, spec 12.2. One row per record (file, run, channel), the lineage dimension
-- of Silver. The lid is the Bronze lid with the layer set to 2, validated on the way.
-- n_samples_src counts source samples including NaN, so Gold derives missing_samples from
-- Silver alone. scale_basis says whether the experiment's microvolt scale is documented in
-- its own README or assumed from the other experiments.
COPY (
    SELECT
        lid_to_uuid(lid_relayer(lid_from_uuid(r.lid), 1)) AS lid,
        r.experiment,
        k.subject_pid,
        r.run,
        r.channel_idx,
        count(*)::BIGINT AS n_samples_src,
        u.scale_basis
    FROM bronze_recording r
    JOIN keyring.key_map k USING (subject_src)
    JOIN (VALUES {{unit_scale_values}}) u(experiment, uv_per_unit, scale_basis)
        ON u.experiment = r.experiment
    GROUP BY ALL
    ORDER BY 1
) TO '{{data_dir}}/silver/record/data_0.parquet' (FORMAT parquet);
