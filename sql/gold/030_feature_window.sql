-- gold/feature_window, spec 3.3 and 12.2. One row per record and 1,000 ms window, with the
-- window's source sample range inside the record. Canary records (spec 12.5) are left out.
COPY (
    SELECT
        experiment,
        subject_pid,
        run,
        channel_idx,
        (ts_ms // 1000 * 1000)::INTEGER AS window_start_ms,
        avg(value_uv)::FLOAT AS mean_uv,
        stddev_pop(value_uv)::FLOAT AS std_uv,
        (max(value_uv) - min(value_uv))::FLOAT AS p2p_uv,
        lid_to_uuid(lid_relayer(lid_from_uuid(lid), 2)) AS lid,
        min(sample_idx)::INTEGER AS sample_lo,
        max(sample_idx)::INTEGER AS sample_hi
    FROM silver_recording
    WHERE lid IN (SELECT lid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 0)
    GROUP BY experiment, subject_pid, run, channel_idx, window_start_ms, lid
    ORDER BY lid, window_start_ms
) TO '{{data_dir}}/gold/feature_window/data_0.parquet' (FORMAT parquet);
