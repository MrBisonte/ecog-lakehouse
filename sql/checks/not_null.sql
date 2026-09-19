-- not_null: rows where the column is NULL. Expected 0.
SELECT count(*) AS observed FROM {{view}} WHERE {{column}} IS NULL
