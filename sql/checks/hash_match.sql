-- hash_match: audit rows whose source file is missing or whose recomputed sha256 differs.
-- Expected 0. The join is on the path below the data root, not the absolute path the row
-- recorded, so moving or renaming the lakehouse does not read as tampering.
SELECT count(*) AS observed
FROM {{view}} a
LEFT JOIN (
    SELECT filename, sha256(content) AS digest FROM read_blob('{{data_dir}}/raw/**/*')
) f ON f.filename = '{{data_dir}}/' || a.source_path_rel
WHERE f.digest IS NULL OR f.digest <> a.sha256
