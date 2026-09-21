-- gold/feature_window, spec 3.3 and 12.2. One row per record and 1,000 ms window, with the
-- window's source sample range inside the record. Canary records (spec 12.5) are left out.
-- The pass over silver/recording groups by lid and window only; the partition strings come
-- from silver/record afterwards, one row per record (see 010_channel_quality.sql).
COPY (
    WITH kept AS (
        SELECT lid, experiment, subject_pid, run, channel_idx
        FROM silver_record
        WHERE lid_radioactive(lid_from_uuid(lid)) = 0
    ),
    windows AS (
        SELECT
            lid,
            (ts_ms // 1000 * 1000)::INTEGER AS window_start_ms,
            avg(value_uv)::FLOAT AS mean_uv,
            stddev_pop(value_uv)::FLOAT AS std_uv,
            (max(value_uv) - min(value_uv))::FLOAT AS p2p_uv,
            min(sample_idx)::INTEGER AS sample_lo,
            max(sample_idx)::INTEGER AS sample_hi
        FROM silver_recording
        WHERE lid IN (SELECT lid FROM kept)
        GROUP BY lid, window_start_ms
    )
    SELECT
        k.experiment,
        k.subject_pid,
        k.run,
        k.channel_idx,
        w.window_start_ms,
        w.mean_uv,
        w.std_uv,
        w.p2p_uv,
        lid_to_uuid(lid_relayer(lid_from_uuid(w.lid), 2)) AS lid,
        w.sample_lo,
        w.sample_hi
    FROM windows w
    JOIN kept k USING (lid)
    ORDER BY lid, w.window_start_ms
) TO '{{data_dir}}/gold/feature_window/data_0.parquet' (FORMAT parquet);
