-- partition_layout: files with a row group over the maximum or fewer row groups than the
-- minimum. Expected 0.
SELECT count(*) AS observed
FROM (
    SELECT file_name,
           count(DISTINCT row_group_id) AS row_groups,
           max(row_group_num_rows) AS max_rows
    FROM parquet_metadata('{{data_dir}}/{{dataset}}/**/*.parquet')
    GROUP BY 1
)
WHERE row_groups < {{min_row_groups}} OR max_rows > {{max_rows_per_row_group}}
