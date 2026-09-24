-- Fault D verification: every file the fix read, fetched once more in full with read_blob and
-- its sha256 compared with docs/data/manifest.json. The check that replaces the CDN's ETag:
-- computed from the bytes, the same answer from every edge. Full downloads, so timed apart.
SET unsafe_disable_etag_checks = true;
WITH published AS (
    SELECT path, sha256 FROM (SELECT unnest(files, recursive := true) FROM read_json(getenv('FAULT_MANIFEST')))
),
fetched AS (
    SELECT filename, sha256(content) AS digest FROM read_blob(getenv('FAULT_FILES')::VARCHAR[])
)
SELECT count(*) AS files, count(*) FILTER (WHERE f.digest <> p.sha256) AS mismatches
FROM fetched f
JOIN published p ON f.filename = getenv('FAULT_BASE') || '/' || p.path;
