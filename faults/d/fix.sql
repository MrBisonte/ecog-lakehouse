-- Fault D fix, spec 6: one statement over every published Parquet file through httpfs, range
-- requests in parallel, nothing copied to disk. FAULT_FILES is a SQL list literal of URLs built
-- from docs/data/manifest.json by bench.sh (plain HTTP has no directory listing to glob).
-- The row count is the same number plant.py prints.
-- GitHub Pages answers the same file with a different ETag from different Fastly edges
-- (seen: MAD and TOJ), so DuckDB's If-Match on the next range request gets a 412. This
-- setting turns that check off; the digests in manifest.json are the integrity check here.
SET unsafe_disable_etag_checks = true;
SELECT count(*) AS rows
FROM read_parquet(getenv('FAULT_FILES')::VARCHAR[], union_by_name = true);
