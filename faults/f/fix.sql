-- Fault F fix, spec 6: retries with a short backoff, the tuned configuration of the DuckDB
-- async I/O post. The plant is the same query with SET http_retries = 0. The aggregate reads
-- every row group, one range request each, so a flaky one in ten bites on every attempt.
SET http_retries = 8;
SET http_retry_wait_ms = 50;
SET http_retry_backoff = 2;
SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet(getenv('FAULT_URL')) GROUP BY 1;
