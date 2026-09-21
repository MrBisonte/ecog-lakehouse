import pytest

from pipeline import convert_mat, db, synth
from tests.conftest import CHANNELS, FILES, SECONDS

SPEC_RECORDING = [
    ("experiment", "VARCHAR"),
    ("subject_src", "VARCHAR"),
    ("run", "SMALLINT"),
    ("channel_idx", "SMALLINT"),
    ("sample_idx", "INTEGER"),
    ("value_raw", "FLOAT"),
    ("ingest_id", "VARCHAR"),
    ("lid", "UUID"),
]
SPEC_AUDIT = [
    ("ingest_id", "VARCHAR"),
    ("source_path", "VARCHAR"),
    ("source_url", "VARCHAR"),
    ("sha256", "VARCHAR"),
    ("bytes", "BIGINT"),
    ("sample_rate_hz", "INTEGER"),
    ("rows_written", "BIGINT"),
    ("tool", "VARCHAR"),
    ("tool_version", "VARCHAR"),
    ("duckdb_version", "VARCHAR"),
    ("ingested_at", "TIMESTAMP"),
]


def describe(con, view):
    return [(r[0], r[1]) for r in con.execute(f"DESCRIBE {view}").fetchall()]


@pytest.fixture(scope="module")
def bronze(built):
    return db.connect()


def test_schemas_match_spec_3_1(bronze):
    assert describe(bronze, "bronze_recording") == SPEC_RECORDING
    assert describe(bronze, "bronze_ingest_audit") == SPEC_AUDIT
    assert [c for c, _ in describe(bronze, "bronze_electrode")] == [
        "experiment", "subject_src", "channel_idx", "x_mm", "y_mm", "z_mm", "brain_area",
        "ingest_id", "lid",
    ]
    assert [c for c, _ in describe(bronze, "bronze_event")] == [
        "experiment", "subject_src", "run", "sample_idx", "event_code", "event_label",
        "ingest_id", "lid",
    ]


def test_row_counts_and_audit(bronze):
    rows = FILES * CHANNELS * SECONDS * 1000
    assert bronze.execute("SELECT count(*) FROM bronze_ingest_audit").fetchone()[0] == FILES
    assert bronze.execute("SELECT count(*) FROM bronze_recording").fetchone()[0] == rows
    assert bronze.execute("SELECT sum(rows_written) FROM bronze_ingest_audit").fetchone()[0] == rows
    events = FILES * SECONDS // 2
    assert bronze.execute("SELECT count(*) FROM bronze_event").fetchone()[0] == events
    assert bronze.execute(
        "SELECT count(*) FROM bronze_event WHERE event_label IS NULL"
    ).fetchone()[0] == 0
    assert bronze.execute("SELECT count(DISTINCT ingest_ord) FROM lineage_dim").fetchone()[0] == FILES
    assert bronze.execute(
        "SELECT count(*) FROM bronze_ingest_audit WHERE tool <> 'convert_mat.py' "
        "OR tool_version IS NULL OR duckdb_version IS NULL OR ingested_at IS NULL"
    ).fetchone()[0] == 0


def test_lid_is_layer_1_and_traces_to_the_audit_row(bronze):
    row = bronze.execute(
        "SELECT lid, ingest_id, channel_idx FROM bronze_recording "
        "WHERE experiment = 'motor_basic' AND channel_idx = 2 LIMIT 1"
    ).fetchone()
    decoded = bronze.execute("SELECT lid_decode(lid_from_uuid(?))", [row[0]]).fetchone()[0]
    assert decoded["layer"] == 1 and decoded["channel"] == 2 and decoded["run"] == 1
    audit = bronze.execute(
        "SELECT source_path, source_url, sha256 FROM bronze_ingest_audit WHERE ingest_id = ?",
        [row[1]],
    ).fetchone()
    trace = bronze.execute("SELECT source_path, source_url, sha256 FROM lid_trace(?)", [row[0]])
    assert trace.fetchone() == audit
    assert audit[1].startswith("synthetic://motor_basic/")


def test_only_the_canary_subject_carries_the_radioactive_bit(bronze):
    rows = bronze.execute(
        "SELECT subject_src, max(lid_radioactive(lid_from_uuid(lid))), min(lid_radioactive(lid_from_uuid(lid))) "
        "FROM (SELECT DISTINCT subject_src, lid FROM bronze_recording) GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert [(s, hi == lo == int(s in convert_mat.CANARY_SUBJECTS)) for s, hi, lo in rows] == [
        (s, True) for s, _, _ in rows
    ]
    assert {s for s, _, _ in rows} == set(synth.SUBJECTS)


def test_rerun_is_a_no_op_and_unknown_directory_is_skipped(bronze, capsys):
    before = bronze.execute("SELECT count(*) FROM bronze_recording").fetchone()[0]
    convert_mat.main([])
    out = capsys.readouterr().out
    assert "no adapter registered for 'mystery'" in out
    assert out.count("sha256 already ingested") == FILES
    assert db.connect().execute("SELECT count(*) FROM bronze_recording").fetchone()[0] == before


def test_connect_removes_an_empty_parquet_left_by_an_aborted_write(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    folder = tmp_path / "gold" / "channel_quality"
    folder.mkdir(parents=True)
    (folder / "data_0.parquet").write_bytes(b"")
    con = db.connect()
    assert not (folder / "data_0.parquet").exists()
    assert "aborted write" in capsys.readouterr().out
    assert con.execute("SELECT count(*) FROM gold_channel_quality").fetchone()[0] == 0
