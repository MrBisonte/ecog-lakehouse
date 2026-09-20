import duckdb
import pytest

from pipeline import db, keyring, synth
from tests.conftest import CHANNELS, FILES, SECONDS

SPEC_RECORDING = [
    ("experiment", "VARCHAR"),
    ("subject_pid", "VARCHAR"),
    ("run", "SMALLINT"),
    ("channel_idx", "SMALLINT"),
    ("ts_ms", "INTEGER"),
    ("value_uv", "FLOAT"),
    ("lid", "UUID"),
    ("sample_idx", "INTEGER"),
]


@pytest.fixture(scope="module")
def silver(built):
    return db.connect()


def test_recording_schema_and_counts(silver):
    assert [(r[0], r[1]) for r in silver.execute("DESCRIBE silver_recording").fetchall()] == SPEC_RECORDING
    nan_rows = len(synth.SUBJECTS) * synth.NAN_BURST_SAMPLES
    assert silver.execute("SELECT count(*) FROM silver_recording").fetchone()[0] == (
        FILES * CHANNELS * SECONDS * 1000 - nan_rows
    )
    assert silver.execute(
        "SELECT count(*) FROM silver_recording WHERE value_uv IS NULL OR isnan(value_uv)"
    ).fetchone()[0] == 0
    assert silver.execute("SELECT max(ts_ms) FROM silver_recording").fetchone()[0] == SECONDS * 1000 - 1
    assert silver.execute("SELECT count(*) FROM silver_record").fetchone()[0] == FILES * CHANNELS
    assert silver.execute("SELECT DISTINCT n_samples_src FROM silver_record").fetchall() == [
        (SECONDS * 1000,)
    ]
    assert silver.execute("SELECT count(*) FROM silver_subject").fetchone()[0] == len(synth.SUBJECTS)
    assert silver.execute("SELECT count(*) FROM silver_event").fetchone()[0] == FILES * SECONDS // 2


def test_no_subject_src_outside_bronze(silver):
    for view in ("silver_subject", "silver_record", "silver_recording", "silver_electrode", "silver_event"):
        cols = [r[0] for r in silver.execute(f"DESCRIBE {view}").fetchall()]
        assert "subject_src" not in cols, view
    pids = silver.execute("SELECT subject_pid FROM silver_subject").fetchall()
    assert all(len(p[0]) == 16 and int(p[0], 16) >= 0 for p in pids)


def test_files_are_sorted_by_lid_then_sample_idx_in_row_groups_under_the_limit(silver, built):
    files = sorted((built / "silver" / "recording").rglob("*.parquet"))
    assert len(files) == FILES
    for f in files:
        unsorted = silver.execute(
            "SELECT count(*) FROM (SELECT lid, sample_idx, "
            "lag(lid) OVER () AS plid, lag(sample_idx) OVER () AS psi "
            f"FROM read_parquet('{f.as_posix()}')) "
            "WHERE plid IS NOT NULL AND (lid, sample_idx) < (plid, psi)"
        ).fetchone()[0]
        assert unsorted == 0, f
        groups = silver.execute(
            "SELECT count(DISTINCT row_group_id), max(row_group_num_rows) "
            f"FROM parquet_metadata('{f.as_posix()}')"
        ).fetchone()
        assert groups[0] >= 2 and groups[1] <= 200000, (f, groups)


def test_silver_lid_is_layer_2_child_of_a_bronze_record(silver):
    row = silver.execute(
        "SELECT lid_layer(lid_from_uuid(lid)), lid_parent(lid) IN (SELECT lid FROM bronze_recording) "
        "FROM silver_record LIMIT 1"
    ).fetchone()
    assert row == (2, True)
    assert silver.execute("SELECT count(*) FROM lid_children(1)").fetchone()[0] == CHANNELS


def test_canary_subject_is_in_silver_with_the_radioactive_bit(silver):
    con = keyring.open_keyring()
    canary_pid = con.execute(
        "SELECT subject_pid FROM key_map WHERE subject_src = ?", [synth.SUBJECTS[-1]]
    ).fetchone()[0]
    con.close()
    per_pid = silver.execute(
        "SELECT subject_pid, max(lid_radioactive(lid_from_uuid(lid))) FROM silver_record GROUP BY 1"
    ).fetchall()
    assert {pid: r for pid, r in per_pid} == {
        pid: int(pid == canary_pid) for pid, _ in per_pid
    }
    assert silver.execute(
        "SELECT count(*) FROM silver_recording WHERE subject_pid = ?", [canary_pid]
    ).fetchone()[0] > 0


def test_reidentification_is_logged_before_it_answers(built):
    con = keyring.open_keyring()
    src, pid = con.execute("SELECT subject_src, subject_pid FROM key_map LIMIT 1").fetchone()
    assert con.execute("SELECT count(*) FROM secret").fetchone()[0] == 1
    con.close()
    assert keyring.pseudonymise(synth.SUBJECTS) == 0, "a rerun adds no pseudonym"
    assert keyring.pseudonymise([*synth.SUBJECTS, "zz"]) == 1
    assert keyring.reidentify(pid, "pytest", "unit test") == src
    assert keyring.reidentify("0000000000000000", "pytest", "unknown pid") is None
    log = duckdb.connect(str(keyring.path()), read_only=True).execute(
        "SELECT actor, purpose, subject_pid FROM access_log ORDER BY accessed_at"
    ).fetchall()
    assert log == [("pytest", "unit test", pid), ("pytest", "unknown pid", "0000000000000000")]
