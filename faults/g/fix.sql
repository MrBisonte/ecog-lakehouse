-- Fault G fix, spec 6: the generator emits a membership list, not a nested OR chain, and it
-- refuses anything that does not parse or nests deeper than pipeline/checks.py MAX_NESTING.
-- This file is the shape pipeline/checks.py produces; plant.py writes the same list for 512
-- channels as fixed.sql next to the two bad variants.
SELECT count(*) FROM silver_record WHERE channel_idx IN (0, 1, 2, 3);
