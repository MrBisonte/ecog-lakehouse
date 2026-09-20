-- Hand written lineage macros, doc/spec.md 12.3. The bit work is in lid_generated.sql, copied
-- from arch-standards by `make lineage` and never edited here. This file adds the lineage
-- tables, the text form, and the navigation: lid_trace, lid_children,
-- lid_parent. Requires the views bronze_ingest_audit, bronze_recording and silver_record
-- (pipeline/db.py connect).

CREATE OR REPLACE TABLE lineage_experiment (code TINYINT, experiment VARCHAR);
INSERT INTO lineage_experiment VALUES (1, 'fingerflex'), (2, 'motor_basic');

CREATE OR REPLACE TABLE lineage_edge (child_lid UUID, parent_lid UUID);

-- ingest_ord is the position of the file in the append-only audit, so it never changes.
-- experiment is not in the audit; the Bronze recording partition of the ingest_id carries it.
CREATE OR REPLACE VIEW lineage_dim AS
SELECT
    row_number() OVER (ORDER BY a.ingested_at, a.sha256)::SMALLINT AS ingest_ord,
    a.ingest_id,
    a.source_path,
    a.source_url,
    a.sha256,
    epoch_ms(a.ingested_at) AS ts_ms,
    r.experiment
FROM bronze_ingest_audit a
LEFT JOIN (SELECT DISTINCT experiment, ingest_id FROM bronze_recording) r USING (ingest_id);

CREATE OR REPLACE MACRO lid_text(lid) AS list_aggregate(
    list_transform(range(26), i -> substr(
        '0123456789ABCDEFGHJKMNPQRSTVWXYZ',
        ((lid_from_uuid(lid) >> (125 - i * 5)::UHUGEINT) & 31)::INTEGER + 1, 1)),
    'string_agg', '');

CREATE OR REPLACE MACRO lid_parse(txt) AS
    CASE WHEN length(txt) <> 26 THEN error('lid_parse: expected 26 characters')
    ELSE lid_to_uuid(list_reduce(
        list_transform(string_split(upper(txt), ''),
            c -> (position(c IN '0123456789ABCDEFGHJKMNPQRSTVWXYZ') - 1)::UHUGEINT),
        (a, d) -> a * 32 + d))
    END;

-- Every loader calls lid_validate: an identifier is carried one layer down only when its
-- layer bits are the ones the loader reads. The radioactive bit travels with it.
CREATE OR REPLACE MACRO lid_relayer(lid, from_layer) AS
    CASE WHEN NOT lid_validate(lid_from_uuid(lid), from_layer)
         THEN error('lid_relayer: layer bits do not match the layer being read')
         ELSE lid_to_uuid(lid_from_uuid(lid) + (1::UHUGEINT << 76))
    END;

CREATE OR REPLACE MACRO lid_parent(lid) AS
    CASE WHEN lid_layer(lid_from_uuid(lid)) <= 1 THEN error('lid_parent: Bronze has no parent')
    ELSE lid_to_uuid(lid_from_uuid(lid) - (1::UHUGEINT << 76))
    END;

-- Bounds of every Silver record of one ingested file: ts_ms and experiment come from the
-- file, layer is 2, run, channel, segment and the canary bit span their full range.
CREATE OR REPLACE MACRO lid_prefix_lo(ing) AS (
    SELECT lid_to_uuid(lid_encode(d.ts_ms, 2, e.code, ing, 0, 0, 0, 0))
    FROM lineage_dim d JOIN lineage_experiment e USING (experiment)
    WHERE d.ingest_ord = ing);

CREATE OR REPLACE MACRO lid_prefix_hi(ing) AS (
    SELECT lid_to_uuid(lid_encode(d.ts_ms, 2, e.code, ing, 15, 1023, 1023, 1) | ((1::UHUGEINT << 23) - 1))
    FROM lineage_dim d JOIN lineage_experiment e USING (experiment)
    WHERE d.ingest_ord = ing);

CREATE OR REPLACE MACRO lid_children(ing) AS TABLE
    SELECT * FROM silver_record
    WHERE lid BETWEEN lid_prefix_lo(ing) AND lid_prefix_hi(ing);

CREATE OR REPLACE MACRO lid_trace(lid) AS TABLE
    SELECT d.source_path, d.source_url, d.sha256, f.ts_ms, f.layer, e.experiment,
           f.run, f.channel, f.segment
    FROM (SELECT lid_decode(lid_from_uuid(lid)) AS f)
    JOIN lineage_dim d ON d.ingest_ord = f.file
    JOIN lineage_experiment e ON e.code = f.experiment;
