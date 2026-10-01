-- gold/channel_quality, spec 3.3. One row per record. Silver carries no amplifier range, so
-- the rails for clipped_pct are the observed extremes of value_uv within the run, the hardware
-- reading; clipped_own_pct measures each record against its own extremes, the signal reading.
-- missing_samples is the record's source sample count minus the samples present in Silver.
-- Canary records (radioactive bit, spec 12.5) never enter a Gold mart.
-- The rails come from the first pass, not from a second aggregate over every sample row.
-- An aggregate computed in the same statement carries no row count: grouping all 871 million
-- rows by experiment, subject_pid and run returns 45 rows, the planner estimates 907 million,
-- and the join to the scan is planned against that. See docs/lessons-learned.md.
COPY (
    WITH kept AS (
        SELECT lid, experiment, subject_pid, run, channel_idx, n_samples_src, scale_basis
        FROM silver_record
        WHERE lid_radioactive(lid_from_uuid(lid)) = 0
    ),
    extremes AS (
        SELECT lid, min(value_uv) AS lo, max(value_uv) AS hi
        FROM silver_recording
        WHERE lid IN (SELECT lid FROM kept)
        GROUP BY lid
    ),
    rails AS (
        SELECT k.experiment, k.subject_pid, k.run, min(e.lo) AS lo, max(e.hi) AS hi
        FROM extremes e
        JOIN kept k USING (lid)
        GROUP BY ALL
    ),
    rails_by_lid AS (
        SELECT k.lid, r.lo, r.hi
        FROM kept k
        JOIN rails r USING (experiment, subject_pid, run)
    ),
    q AS (
        SELECT
            r.lid,
            count(*)::BIGINT AS n_samples,
            sqrt(avg(r.value_uv * r.value_uv))::FLOAT AS rms_uv,
            (100.0 * count(*) FILTER (WHERE r.value_uv = b.lo OR r.value_uv = b.hi)
                / count(*))::FLOAT AS clipped_pct,
            (100.0 * count(*) FILTER (WHERE r.value_uv = e.lo OR r.value_uv = e.hi)
                / count(*))::FLOAT AS clipped_own_pct
        FROM silver_recording r
        JOIN rails_by_lid b USING (lid)
        JOIN extremes e USING (lid)
        GROUP BY r.lid
    )
    SELECT
        k.experiment,
        k.subject_pid,
        k.run,
        k.channel_idx,
        q.n_samples,
        (k.n_samples_src - q.n_samples)::BIGINT AS missing_samples,
        q.rms_uv,
        q.clipped_pct,
        q.clipped_own_pct,
        n.line_noise_ratio::FLOAT AS line_noise_ratio,
        k.scale_basis,
        lid_to_uuid(lid_relayer(lid_from_uuid(q.lid), 2)) AS lid
    FROM q
    JOIN kept k USING (lid)
    LEFT JOIN line_noise n USING (lid)
    ORDER BY 1, 2, 3, 4
) TO '{{data_dir}}/gold/channel_quality/data_0.parquet' (FORMAT parquet);
