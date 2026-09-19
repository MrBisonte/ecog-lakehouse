-- unique: groups of the columns that occur more than once. Expected 0.
SELECT count(*) AS observed
FROM (SELECT 1 FROM {{view}} GROUP BY {{columns}} HAVING count(*) > 1)
