-- bronze/ingest_audit, spec 3.1. One file per converted source file, never rewritten.
COPY (
    SELECT
        '{{ingest_id}}' AS ingest_id,
        '{{data_root}}' AS data_root,
        '{{source_path_rel}}' AS source_path_rel,
        '{{source_url}}' AS source_url,
        '{{sha256}}' AS sha256,
        {{bytes}}::BIGINT AS bytes,
        {{sample_rate_hz}}::INTEGER AS sample_rate_hz,
        {{rows_written}}::BIGINT AS rows_written,
        '{{tool}}' AS tool,
        '{{tool_version}}' AS tool_version,
        '{{duckdb_version}}' AS duckdb_version,
        '{{ingest_host}}' AS ingest_host,
        TIMESTAMP '{{ingested_at}}' AS ingested_at
) TO '{{data_dir}}/bronze/ingest_audit/{{ingest_id}}.parquet' (FORMAT parquet);
