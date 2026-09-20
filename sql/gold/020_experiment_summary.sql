-- gold/experiment_summary, spec 3.3. One row per experiment and subject. duration_s is the
-- sum over runs of the last present sample time plus one millisecond. A subject whose
-- records carry the canary bit (spec 12.5) is left out.
COPY (
    WITH canary AS (
        SELECT DISTINCT subject_pid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 1
    ),
    runs AS (
        SELECT experiment, subject_pid, run,
               count(DISTINCT channel_idx) AS n_channels,
               max(ts_ms) + 1 AS duration_ms
        FROM silver_recording
        WHERE subject_pid NOT IN (SELECT subject_pid FROM canary)
        GROUP BY ALL
    ),
    events AS (
        SELECT experiment, subject_pid, count(*) AS n_events
        FROM silver_event
        GROUP BY ALL
    )
    SELECT
        r.experiment,
        r.subject_pid,
        count(*)::SMALLINT AS n_runs,
        max(r.n_channels)::SMALLINT AS n_channels,
        (sum(r.duration_ms) / 1000.0)::FLOAT AS duration_s,
        coalesce(any_value(e.n_events), 0)::INTEGER AS n_events
    FROM runs r
    LEFT JOIN events e USING (experiment, subject_pid)
    GROUP BY 1, 2
    ORDER BY 1, 2
) TO '{{data_dir}}/gold/experiment_summary/data_0.parquet' (FORMAT parquet);
