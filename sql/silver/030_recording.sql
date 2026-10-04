-- silver/recording, spec 3.2 and 12.2. Microvolts, milliseconds, pseudonyms. A sample
-- that is NULL in Bronze, a NaN in the source, is dropped.
-- Executed once per (experiment, subject_pid) partition by pipeline/run.py: DuckDB 1.5's
-- partitioned COPY does not keep the ORDER BY across its buffer flushes, a plain COPY does.
-- Sorted by lid, sample_idx inside the file. Row groups of at most 200,000 rows: DuckDB
-- rounds the size up to a multiple of 2048, so 198,656 is the largest value under the limit.
-- Parquet version 2, ADR-0007: ts_ms and sample_idx rise by a constant step inside a record and
-- are stored as deltas; version 1 stored them plain, 78 percent of the layer's bytes.
COPY (
    SELECT
        r.experiment,
        k.subject_pid,
        r.run,
        r.channel_idx,
        (r.sample_idx::BIGINT * 1000 / a.sample_rate_hz)::INTEGER AS ts_ms,
        (r.value_raw * u.uv_per_unit)::FLOAT AS value_uv,
        s.lid,
        r.sample_idx
    FROM bronze_recording r
    JOIN keyring.key_map k USING (subject_src)
    JOIN bronze_ingest_audit a USING (ingest_id)
    JOIN (SELECT lid, lid_parent(lid) AS bronze_lid FROM silver_record) s ON s.bronze_lid = r.lid
    JOIN (VALUES {{unit_scale_values}}) u(experiment, uv_per_unit, scale_basis) ON u.experiment = r.experiment
    WHERE r.experiment = '{{experiment}}' AND k.subject_pid = '{{subject_pid}}'
      AND r.value_raw IS NOT NULL AND NOT isnan(r.value_raw)
    ORDER BY s.lid, r.sample_idx
) TO '{{data_dir}}/silver/recording/experiment={{experiment}}/subject_pid={{subject_pid}}/data_0.parquet'
(FORMAT parquet, PARQUET_VERSION v2, ROW_GROUP_SIZE 198656);
