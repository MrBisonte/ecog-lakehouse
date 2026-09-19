-- silver/subject, spec 3.2. One row per pseudonym present in Bronze.
COPY (
    SELECT k.subject_pid, k.created_at AS first_seen_at
    FROM keyring.key_map k
    JOIN (SELECT DISTINCT subject_src FROM bronze_recording) b USING (subject_src)
    ORDER BY 1
) TO '{{data_dir}}/silver/subject/data_0.parquet' (FORMAT parquet);
