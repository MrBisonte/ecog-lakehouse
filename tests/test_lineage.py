import duckdb
import pytest

from pipeline import db
from pipeline.lid import ALPHABET, ulid

ENCODE = "SELECT lid_to_uuid(lid_encode(?, ?, ?, ?, ?, ?, ?, ?))"
FIELDS = ["ts_ms", "layer", "experiment", "file", "run", "channel", "segment", "radioactive"]
CASES = {
    "typical": (1789819200000, 2, 1, 3, 1, 17, 0, 0),
    "canary": (1789819200000, 2, 2, 4, 1, 5, 0, 1),
    "zeros": (0, 0, 0, 0, 0, 0, 0, 0),
    "maxes": (2**48 - 1, 15, 255, 65535, 15, 1023, 1023, 1),
}


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return db.connect()


def encode(con, parts):
    return con.execute(ENCODE, list(parts)).fetchone()[0]


def decode(con, lid):
    return con.execute("SELECT lid_decode(lid_from_uuid(?))", [lid]).fetchone()[0]


@pytest.mark.parametrize("parts", CASES.values(), ids=CASES.keys())
def test_generated_encode_and_decode_round_trip_every_field(con, parts):
    assert [decode(con, encode(con, parts))[f] for f in FIELDS] == list(parts)


def test_no_field_straddles_the_64_bit_boundary(con):
    x = encode(con, CASES["maxes"])
    hi, lo = con.execute(
        "SELECT (lid_from_uuid(?) >> 64)::UBIGINT, (lid_from_uuid(?) & ((1::UHUGEINT << 64) - 1))::UBIGINT",
        [x, x],
    ).fetchone()
    assert (hi >> 16, (hi >> 12) & 15, (hi >> 4) & 255, hi & 0xF) == (2**48 - 1, 15, 255, 0)
    assert (lo >> 48, (lo >> 44) & 15, (lo >> 34) & 1023, (lo >> 24) & 1023) == (65535, 15, 1023, 1023)
    assert (lo >> 23) & 1 == 1 and lo & 0x7FFFFF == 0


def test_text_is_26_crockford_characters_and_parse_inverts(con):
    x = encode(con, CASES["typical"])
    text = con.execute("SELECT lid_text(lid_from_uuid(?))", [x]).fetchone()[0]
    assert len(text) == 26 and set(text) <= set(ALPHABET)
    assert con.execute("SELECT lid_to_uuid(lid_parse(?)) = ?", [text, x]).fetchone()[0]
    with pytest.raises(duckdb.Error, match="26 characters"):
        con.execute("SELECT lid_parse('short')").fetchone()


def test_python_ulid_and_sql_text_agree(con):
    u = ulid()
    assert len(u) == 26 and set(u) <= set(ALPHABET)
    assert con.execute("SELECT lid_text(lid_parse(?))", [u]).fetchone()[0] == u


def test_parent_decrements_layer_only_and_relayer_validates(con):
    parts = CASES["canary"]
    silver = encode(con, parts)
    parent = con.execute("SELECT lid_parent(?)", [silver]).fetchone()[0]
    assert parent == encode(con, (parts[0], 1, *parts[2:]))
    assert con.execute("SELECT lid_to_uuid(lid_relayer(lid_from_uuid(?), 1))", [parent]).fetchone()[0] == silver
    assert con.execute("SELECT lid_validate(lid_from_uuid(?), 2), lid_radioactive(lid_from_uuid(?))", [silver, silver]).fetchone() == (True, 1)
    with pytest.raises(duckdb.Error, match="Bronze has no parent"):
        con.execute("SELECT lid_parent(?)", [parent]).fetchone()
    with pytest.raises(duckdb.Error, match="layer bits do not match"):
        con.execute("SELECT lid_relayer(lid_from_uuid(?), 1)", [silver]).fetchone()


def lineage_fixture(con):
    """Three ingested files, records for each, as the macros would see them after Silver."""
    con.execute(
        "CREATE OR REPLACE VIEW bronze_ingest_audit AS SELECT * FROM (VALUES "
        "('I1', '/lake', 'raw/a.mat', 'https://x/a', 'ha', TIMESTAMP '2026-09-19 10:00:00'), "
        "('I2', '/lake', 'raw/b.mat', 'https://x/b', 'hb', TIMESTAMP '2026-09-19 10:00:01'), "
        "('I3', '/lake', 'raw/c.mat', 'https://x/c', 'hc', TIMESTAMP '2026-09-19 10:00:02')) "
        "t(ingest_id, data_root, source_path_rel, source_url, sha256, ingested_at)"
    )
    con.execute(
        "CREATE OR REPLACE VIEW bronze_recording AS SELECT * FROM (VALUES "
        "('fingerflex', 'I1'), ('motor_basic', 'I2'), ('fingerflex', 'I3')) "
        "t(experiment, ingest_id)"
    )
    con.execute(
        "CREATE OR REPLACE VIEW silver_record AS "
        "SELECT lid_to_uuid(lid_encode(d.ts_ms, 2, e.code, d.ingest_ord, r.run, r.ch, 0, r.rad)) AS lid, "
        "d.experiment, 'pid' AS subject_pid, r.run::SMALLINT AS run, "
        "r.ch::SMALLINT AS channel_idx, 1000::BIGINT AS n_samples_src "
        "FROM lineage_dim d JOIN lineage_experiment e USING (experiment), "
        "(VALUES (1, 0, 0), (1, 1, 0), (2, 5, 1)) r(run, ch, rad)"
    )


def test_children_returns_exactly_the_records_of_one_ingest(con):
    lineage_fixture(con)
    assert con.execute("SELECT count(*) FROM silver_record").fetchone()[0] == 9
    got = con.execute("SELECT lid FROM lid_children(2) ORDER BY lid").fetchall()
    want = con.execute(
        "SELECT lid FROM silver_record WHERE lid_file(lid_from_uuid(lid)) = 2 ORDER BY lid"
    ).fetchall()
    assert len(got) == 3 and got == want


def test_trace_on_a_bronze_row_returns_the_ingested_file(con):
    lineage_fixture(con)
    bronze = con.execute(
        "SELECT lid_to_uuid(lid_encode(ts_ms, 1, 2, ingest_ord, 1, 17, 0, 0)) FROM lineage_dim "
        "WHERE ingest_id = 'I2'"
    ).fetchone()[0]
    cursor = con.execute("SELECT * FROM lid_trace(?)", [bronze])
    cols = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    assert cols == [
        "source_path", "source_url", "sha256", "ts_ms", "layer", "experiment",
        "run", "channel", "segment",
    ]
    assert row[:3] == ("/lake/raw/b.mat", "https://x/b", "hb"), "the root and the path join here"
    assert row[4:] == (1, "motor_basic", 1, 17, 0)
