-- sql at severity flag: the records the requirement's own query found, not how many. A failure
-- is recorded and does not stop the build, so the evidence has to name what to go and look at.
-- The query returns one column, `offender`, already ordered. Expected: 'no records'.
WITH found AS ({{query}})
SELECT CASE WHEN count(*) = 0 THEN 'no records'
            ELSE count(*)::VARCHAR || ' of ' || (SELECT count(*) FROM {{view}})::VARCHAR || ': '
                 || list_aggregate(list_slice(list(offender), 1, 5), 'string_agg', ', ')
                 || CASE WHEN count(*) > 5 THEN ' and more' ELSE '' END
       END AS observed
FROM found;
