-- gold/feature_window, spec 3.3 and 12.2. One row per record and 1,000 ms window, with the
-- window's source sample range inside the record.
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
        lid_from_u128(lid_u128(lid) + (1::UHUGEINT << 76)) AS lid,
        min(sample_idx)::INTEGER AS sample_lo,
        max(sample_idx)::INTEGER AS sample_hi
    FROM silver_recording
    GROUP BY experiment, subject_pid, run, channel_idx, window_start_ms, lid
    ORDER BY lid, window_start_ms
) TO '{{data_dir}}/gold/feature_window/data_0.parquet' (FORMAT parquet);
