-- gold/channel_quality, spec 3.3. One row per record. Silver carries no amplifier range, so
-- the rails for clipped_pct are the observed extremes of value_uv within the run.
-- missing_samples is the record's source sample count minus the samples present in Silver.
-- Canary records (radioactive bit, spec 12.5) never enter a Gold mart.
COPY (
    WITH rails AS (
        SELECT experiment, subject_pid, run, min(value_uv) AS lo, max(value_uv) AS hi
        FROM silver_recording
        GROUP BY ALL
    ),
    q AS (
        SELECT
            r.experiment,
            r.subject_pid,
            r.run,
            r.channel_idx,
            r.lid,
            count(*)::BIGINT AS n_samples,
            sqrt(avg(r.value_uv * r.value_uv))::FLOAT AS rms_uv,
            (100.0 * count(*) FILTER (WHERE r.value_uv = rails.lo OR r.value_uv = rails.hi)
                / count(*))::FLOAT AS clipped_pct
        FROM silver_recording r
        JOIN rails USING (experiment, subject_pid, run)
        WHERE r.lid IN (SELECT lid FROM silver_record WHERE lid_radioactive(lid_u128(lid)) = 0)
        GROUP BY ALL
    )
    SELECT
        q.experiment,
        q.subject_pid,
        q.run,
        q.channel_idx,
        q.n_samples,
        (s.n_samples_src - q.n_samples)::BIGINT AS missing_samples,
        q.rms_uv,
        q.clipped_pct,
        n.line_noise_ratio::FLOAT AS line_noise_ratio,
        lid_relayer(q.lid, 2) AS lid
    FROM q
    JOIN silver_record s USING (lid)
    LEFT JOIN line_noise n USING (lid)
    ORDER BY 1, 2, 3, 4
) TO '{{data_dir}}/gold/channel_quality/data_0.parquet' (FORMAT parquet);
