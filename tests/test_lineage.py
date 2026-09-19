import duckdb
import pytest

from pipeline import db
from pipeline.lid import ALPHABET, ulid

ENCODE = "SELECT lid_encode(?, ?, ?, ?, ?, ?, ?)"
FIELDS = ["ts_ms", "layer", "experiment", "ingest_ord", "run", "channel", "segment"]
CASES = {
    "typical": (1789819200000, 2, 1, 3, 1, 17, 0),
    "zeros": (0, 0, 0, 0, 0, 0, 0),
    "maxes": (2**48 - 1, 15, 255, 65535, 15, 1023, 1023),
}


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return db.connect()


def encode(con, parts):
    return con.execute(ENCODE, list(parts)).fetchone()[0]


@pytest.mark.parametrize("parts", CASES.values(), ids=CASES.keys())
def test_encode_decode_round_trips_every_field(con, parts):
    decoded = con.execute("SELECT lid_decode(?)", [encode(con, parts)]).fetchone()[0]
    assert [decoded[f] for f in FIELDS] == list(parts)


def test_text_is_26_crockford_characters_and_parse_inverts(con):
    x = encode(con, CASES["typical"])
    text = con.execute("SELECT lid_text(?)", [x]).fetchone()[0]
    assert len(text) == 26 and set(text) <= set(ALPHABET)
    assert con.execute("SELECT lid_parse(?) = ?", [text, x]).fetchone()[0]


def test_python_ulid_and_sql_text_agree(con):
    u = ulid()
    assert len(u) == 26 and set(u) <= set(ALPHABET)
    assert con.execute("SELECT lid_text(lid_parse(?))", [u]).fetchone()[0] == u


def test_parent_decrements_layer_only(con):
    parts = CASES["typical"]
    parent = con.execute("SELECT lid_parent(?)", [encode(con, parts)]).fetchone()[0]
    assert parent == encode(con, (parts[0], 1, *parts[2:]))
    with pytest.raises(duckdb.Error, match="Bronze has no parent"):
        con.execute("SELECT lid_parent(?)", [parent]).fetchone()


def test_out_of_range_field_is_an_error(con):
    with pytest.raises(duckdb.Error, match="out of range"):
        encode(con, (0, 1, 1, 1, 1, 1024, 0))
    with pytest.raises(duckdb.Error, match="26 characters"):
        con.execute("SELECT lid_parse('short')").fetchone()


def lineage_fixture(con):
    """Three ingested files, records for each, as the macros would see them after Silver."""
    con.execute(
        "CREATE OR REPLACE VIEW bronze_ingest_audit AS SELECT * FROM (VALUES "
        "('I1', 'raw/a.mat', 'https://x/a', 'ha', TIMESTAMP '2026-09-19 10:00:00'), "
        "('I2', 'raw/b.mat', 'https://x/b', 'hb', TIMESTAMP '2026-09-19 10:00:01'), "
        "('I3', 'raw/c.mat', 'https://x/c', 'hc', TIMESTAMP '2026-09-19 10:00:02')) "
        "t(ingest_id, source_path, source_url, sha256, ingested_at)"
    )
    con.execute(
        "CREATE OR REPLACE VIEW bronze_recording AS SELECT * FROM (VALUES "
        "('fingerflex', 'I1'), ('motor_basic', 'I2'), ('fingerflex', 'I3')) "
        "t(experiment, ingest_id)"
    )
    con.execute(
        "CREATE OR REPLACE VIEW silver_record AS "
        "SELECT lid_encode(d.ts_ms, 2, e.code, d.ingest_ord, r.run, r.ch, 0) AS lid, "
        "d.experiment, 'pid' AS subject_pid, r.run::SMALLINT AS run, "
        "r.ch::SMALLINT AS channel_idx, 1000::BIGINT AS n_samples_src "
        "FROM lineage_dim d JOIN lineage_experiment e USING (experiment), "
        "(VALUES (1, 0), (1, 1), (2, 5)) r(run, ch)"
    )


def test_children_returns_exactly_the_records_of_one_ingest(con):
    lineage_fixture(con)
    assert con.execute("SELECT count(*) FROM silver_record").fetchone()[0] == 9
    got = con.execute("SELECT lid FROM lid_children(2) ORDER BY lid").fetchall()
    want = con.execute(
        "SELECT lid FROM silver_record WHERE lid_decode(lid).ingest_ord = 2 ORDER BY lid"
    ).fetchall()
    assert len(got) == 3 and got == want


def test_trace_on_a_bronze_row_returns_the_ingested_file(con):
    lineage_fixture(con)
    bronze = con.execute(
        "SELECT lid_encode(ts_ms, 1, 2, ingest_ord, 1, 17, 0) FROM lineage_dim WHERE ingest_id = 'I2'"
    ).fetchone()[0]
    row = con.execute("SELECT * FROM lid_trace(?)", [bronze]).fetchone()
    cols = [d[0] for d in con.execute("SELECT * FROM lid_trace(?)", [bronze]).description]
    assert cols == [
        "source_path", "source_url", "sha256", "ts_ms", "layer", "experiment",
        "run", "channel", "segment",
    ]
    assert row[:3] == ("raw/b.mat", "https://x/b", "hb")
    assert row[4:] == (1, "motor_basic", 1, 17, 0)
