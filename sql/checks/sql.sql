-- sql: rows returned by the requirement's own query. Expected 0.
SELECT count(*) AS observed FROM ({{query}})
