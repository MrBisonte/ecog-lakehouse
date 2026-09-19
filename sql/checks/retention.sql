-- retention: age in days of the oldest Parquet file of the dataset, gathered by the generator
-- from file modification times (DuckDB 1.5 exposes no file time). Expected at most max_age_days.
SELECT {{oldest_age_days}} AS observed
