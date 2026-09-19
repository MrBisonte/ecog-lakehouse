-- no_direct_identifier: forbidden columns present in the dataset. Expected 0.
SELECT count(*) AS observed
FROM information_schema.columns
WHERE table_name = '{{view}}' AND column_name IN ({{forbidden_columns}})
