"""The audit row commits an ingest: readers see only audited rows, a failed ingest leaves no
visible trace, and the next ingest moves its files to quarantine before writing again."""

import pytest

from pipeline import convert_mat, db, keyring, run, synth

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


def test_rerun_after_a_failure_ingests_once_and_quarantines_the_orphan(one_file, monkeypatch, capsys):
    with monkeypatch.context() as patch:
        fail_before_audit(patch)
        with pytest.raises(RuntimeError):
            convert_mat.main([])
    orphan = {p.relative_to(one_file) for p in data_files(one_file)}
    orphan_id = db.connect().execute(
        f"SELECT DISTINCT ingest_id FROM read_parquet('{one_file.as_posix()}/bronze/recording/**/*.parquet')"
    ).fetchall()
    assert len(orphan_id) == 1
    orphan_id = orphan_id[0][0]
    capsys.readouterr()

    assert convert_mat.main([]) == 0
    out = capsys.readouterr().out
    assert out.count(f"quarantined {orphan_id}") == 1, out
    moved = {p.relative_to(one_file / "quarantine" / orphan_id) for p in data_files(one_file, "quarantine")}
    assert moved == orphan
    assert not any(p.relative_to(one_file) in orphan for p in data_files(one_file))
    assert not list((one_file / "bronze" / "recording").rglob(f"ingest_id={orphan_id}"))

    assert run.main(["silver"]) == 0
    con = db.connect()
    assert con.execute("SELECT count(*) FROM bronze_ingest_audit").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM silver_electrode").fetchone()[0] == CHANNELS
    assert con.execute("SELECT count(*) FROM silver_record").fetchone()[0] == CHANNELS
    assert con.execute(
        "SELECT count(*) FROM silver_record r WHERE NOT EXISTS "
        "(SELECT 1 FROM silver_recording s WHERE s.lid = r.lid)"
    ).fetchone()[0] == 0


def test_a_keyring_failure_writes_nothing_to_bronze(one_file, monkeypatch):
    def host():
        raise RuntimeError("keyring.duckdb is held by another process")

    monkeypatch.setattr(keyring, "host", host)
    with pytest.raises(RuntimeError):
        convert_mat.main([])
    assert data_files(one_file) == []


def test_a_clean_bronze_moves_nothing_and_prints_nothing(one_file, capsys):
    assert convert_mat.main([]) == 0
    before = data_files(one_file)
    capsys.readouterr()
    assert convert_mat.main([]) == 0
    assert "quarantine" not in capsys.readouterr().out
    assert data_files(one_file) == before
    assert not (one_file / "quarantine").exists()
