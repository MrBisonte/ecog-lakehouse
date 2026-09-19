-- Lineage identifier macros, doc/spec.md section 12.
-- Layout of the 128 bits, most significant first:
--   ts_ms 48, layer 4, experiment 8, ingest_ord 16, run 4, channel 10, segment 10, reserved 28.
-- DuckDB 1.5 has no UUID to integer cast, so the bridge is hex text to BIT to UHUGEINT.
-- Requires the views bronze_ingest_audit and silver_record to exist (pipeline/db.py connect).

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

CREATE OR REPLACE MACRO lid_u128(lid) AS
    from_hex(replace(lid::VARCHAR, '-', ''))::BIT::UHUGEINT;

CREATE OR REPLACE MACRO lid_hex32(x) AS lpad(hex(x::UHUGEINT), 32, '0');

CREATE OR REPLACE MACRO lid_from_u128(x) AS (
    substr(lid_hex32(x), 1, 8) || '-' || substr(lid_hex32(x), 9, 4) || '-'
    || substr(lid_hex32(x), 13, 4) || '-' || substr(lid_hex32(x), 17, 4) || '-'
    || substr(lid_hex32(x), 21, 12)
)::UUID;

CREATE OR REPLACE MACRO lid_encode(ts_ms, layer, exp, ing, run, ch, seg) AS
    CASE
        WHEN ts_ms < 0 OR ts_ms >= 281474976710656 OR layer NOT BETWEEN 0 AND 15
            OR exp NOT BETWEEN 0 AND 255 OR ing NOT BETWEEN 0 AND 65535
            OR run NOT BETWEEN 0 AND 15 OR ch NOT BETWEEN 0 AND 1023
            OR seg NOT BETWEEN 0 AND 1023
        THEN error('lid_encode: field out of range')
        ELSE lid_from_u128(
            (ts_ms::UHUGEINT << 80) | (layer::UHUGEINT << 76) | (exp::UHUGEINT << 68)
            | (ing::UHUGEINT << 52) | (run::UHUGEINT << 48) | (ch::UHUGEINT << 38)
            | (seg::UHUGEINT << 28))
    END;

CREATE OR REPLACE MACRO lid_decode(lid) AS {
    'ts_ms': (lid_u128(lid) >> 80)::BIGINT,
    'layer': ((lid_u128(lid) >> 76) & 15)::TINYINT,
    'experiment': ((lid_u128(lid) >> 68) & 255)::SMALLINT,
    'ingest_ord': ((lid_u128(lid) >> 52) & 65535)::INTEGER,
    'run': ((lid_u128(lid) >> 48) & 15)::SMALLINT,
    'channel': ((lid_u128(lid) >> 38) & 1023)::SMALLINT,
    'segment': ((lid_u128(lid) >> 28) & 1023)::SMALLINT
};

CREATE OR REPLACE MACRO lid_text(lid) AS list_aggregate(
    list_transform(range(26), i -> substr(
        '0123456789ABCDEFGHJKMNPQRSTVWXYZ',
        ((lid_u128(lid) >> (125 - i * 5)::UHUGEINT) & 31)::INTEGER + 1, 1)),
    'string_agg', '');

CREATE OR REPLACE MACRO lid_parse(txt) AS
    CASE WHEN length(txt) <> 26 THEN error('lid_parse: expected 26 characters')
    ELSE lid_from_u128(list_reduce(
        list_transform(string_split(upper(txt), ''),
            c -> (position(c IN '0123456789ABCDEFGHJKMNPQRSTVWXYZ') - 1)::UHUGEINT),
        (a, d) -> a * 32 + d))
    END;

CREATE OR REPLACE MACRO lid_parent(lid) AS
    CASE WHEN ((lid_u128(lid) >> 76) & 15) <= 1 THEN error('lid_parent: Bronze has no parent')
    ELSE lid_from_u128(lid_u128(lid) - (1::UHUGEINT << 76))
    END;

-- Bounds of every Silver record of one ingested file: ts_ms and experiment come from the
-- file, layer is 2, run, channel and segment span their full range.
CREATE OR REPLACE MACRO lid_prefix_lo(ing) AS (
    SELECT lid_encode(d.ts_ms, 2, e.code, ing, 0, 0, 0)
    FROM lineage_dim d JOIN lineage_experiment e ON e.experiment = d.experiment
    WHERE d.ingest_ord = ing);

CREATE OR REPLACE MACRO lid_prefix_hi(ing) AS (
    SELECT lid_from_u128(lid_u128(lid_encode(d.ts_ms, 2, e.code, ing, 15, 1023, 1023))
        | ((1::UHUGEINT << 28) - 1))
    FROM lineage_dim d JOIN lineage_experiment e ON e.experiment = d.experiment
    WHERE d.ingest_ord = ing);

CREATE OR REPLACE MACRO lid_children(ing) AS TABLE
    SELECT * FROM silver_record
    WHERE lid BETWEEN lid_prefix_lo(ing) AND lid_prefix_hi(ing);

CREATE OR REPLACE MACRO lid_trace(lid) AS TABLE
    SELECT d.source_path, d.source_url, d.sha256, f.ts_ms, f.layer, e.experiment,
           f.run, f.channel, f.segment
    FROM (SELECT lid_decode(lid) AS f)
    JOIN lineage_dim d ON d.ingest_ord = f.ingest_ord
    JOIN lineage_experiment e ON e.code = f.experiment;
