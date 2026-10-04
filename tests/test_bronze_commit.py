"""The audit row commits an ingest: readers see only audited rows, a failed ingest leaves no
visible trace, and the next ingest moves its files to quarantine before writing again."""

import pytest

from pipeline import convert_mat, db, synth

CHANNELS = 4
BRONZE = ("bronze_recording", "bronze_electrode", "bronze_event")


@pytest.fixture
def one_file(tmp_path, monkeypatch):
    """A fresh DATA_DIR holding one synthetic raw file."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    synth.main(["--seconds", "2", "--channels", str(CHANNELS), "--canary", "fingerflex"])
    return tmp_path


def fail_before_audit(monkeypatch):
    """Every Bronze COPY runs, then the audit step raises, as a kill there would leave it."""
    original = db.run_sql

    def run_sql(con, path, **values):
        if path.name == "ingest_audit.sql":
            raise RuntimeError("killed before the audit row")
        original(con, path, **values)

    monkeypatch.setattr(db, "run_sql", run_sql)


def data_files(root, folder="bronze"):
    return sorted((root / folder).rglob("*.parquet"))


def test_rows_without_an_audit_row_are_not_read(one_file, monkeypatch):
    fail_before_audit(monkeypatch)
    with pytest.raises(RuntimeError):
        convert_mat.main([])
    assert data_files(one_file), "the data COPYs ran"
    con = db.connect()
    for view in BRONZE:
        assert con.execute(f"SELECT count(*) FROM {view}").fetchone()[0] == 0, view
