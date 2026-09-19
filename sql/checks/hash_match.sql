-- hash_match: audit rows whose source file is missing or whose recomputed sha256 differs.
-- Expected 0.
SELECT count(*) AS observed
FROM {{view}} a
LEFT JOIN (
    SELECT filename, sha256(content) AS digest FROM read_blob('{{data_dir}}/raw/**/*')
) f ON f.filename = a.source_path
WHERE f.digest IS NULL OR f.digest <> a.sha256
