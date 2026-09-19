"""One unit test per check kind of spec 5.2, on tiny datasets in a temporary DATA_DIR."""

import hashlib
import os
import time

import duckdb
import pytest

from pipeline import checks, db


@pytest.fixture
def write(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def _write(dataset, select, options=""):
        folder = tmp_path / dataset
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "data_0.parquet"
        duckdb.connect().execute(f"COPY ({select}) TO '{path.as_posix()}' (FORMAT parquet {options})")
        return path

    return _write


def outcome(kind, dataset, params):
    [check] = checks.generate("test", "T-1", kind, dataset, params)
    [row] = checks.run(db.connect(), [check])
    return row["result"], row["observed"], row["expected"]


def test_not_null(write):
    write("silver/subject", "SELECT 'a' AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    assert outcome("not_null", "silver/subject", {"column": "subject_pid"}) == ("pass", "0", "0")
    write("silver/subject", "SELECT NULL::VARCHAR AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    assert outcome("not_null", "silver/subject", {"column": "subject_pid"}) == ("fail", "1", "0")


def test_unique(write):
    write("silver/subject", "SELECT unnest(['a', 'b']) AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    assert outcome("unique", "silver/subject", {"columns": ["subject_pid"]})[0] == "pass"
    write("silver/subject", "SELECT unnest(['a', 'a']) AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    assert outcome("unique", "silver/subject", {"columns": ["subject_pid"]}) == ("fail", "1", "0")


def test_row_count_min(write):
    write("silver/subject", "SELECT unnest(['a', 'b']) AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    assert outcome("row_count_min", "silver/subject", {"min": 2}) == ("pass", "2", "2")
    assert outcome("row_count_min", "silver/subject", {"min": 3}) == ("fail", "2", "3")


def test_no_direct_identifier(write):
    write("gold/experiment_summary", "SELECT 'x' AS experiment, 'p' AS subject_pid")
    params = {"forbidden_columns": ["subject_src"]}
    assert outcome("no_direct_identifier", "gold/experiment_summary", params) == ("pass", "0", "0")
    write("gold/experiment_summary", "SELECT 'x' AS experiment, 'aa' AS subject_src")
    assert outcome("no_direct_identifier", "gold/experiment_summary", params) == ("fail", "1", "0")


def test_hash_match(write, tmp_path):
    raw = tmp_path / "raw" / "synthetic" / "x.bin"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"original bytes")
    digest = hashlib.sha256(b"original bytes").hexdigest()
    write(
        "bronze/ingest_audit",
        f"SELECT 'I1' AS ingest_id, '{raw.as_posix()}' AS source_path, 'u' AS source_url, "
        f"'{digest}' AS sha256, 14::BIGINT AS bytes, 1000 AS sample_rate_hz, 1::BIGINT AS rows_written, "
        "'t' AS tool, 'v' AS tool_version, 'd' AS duckdb_version, now()::TIMESTAMP AS ingested_at",
    )
    assert outcome("hash_match", "bronze/ingest_audit", {}) == ("pass", "0", "0")
    raw.write_bytes(b"tampered bytes")
    assert outcome("hash_match", "bronze/ingest_audit", {}) == ("fail", "1", "0")
    raw.unlink()
    assert outcome("hash_match", "bronze/ingest_audit", {}) == ("fail", "1", "0")


def test_partition_layout(write):
    write("silver/subject", "SELECT i::VARCHAR AS subject_pid, now()::TIMESTAMP AS first_seen_at FROM range(5000) t(i)", ", ROW_GROUP_SIZE 2048")
    ok = {"max_rows_per_row_group": 2048, "min_row_groups": 2}
    assert outcome("partition_layout", "silver/subject", ok) == ("pass", "0", "0")
    assert outcome("partition_layout", "silver/subject", {**ok, "max_rows_per_row_group": 2000})[0] == "fail"
    assert outcome("partition_layout", "silver/subject", {**ok, "min_row_groups": 4})[0] == "fail"


def test_retention(write):
    path = write("silver/subject", "SELECT 'a' AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    assert outcome("retention", "silver/subject", {"max_age_days": 1})[0] == "pass"
    old = time.time() - 10 * 86400
    os.utime(path, (old, old))
    result, observed, expected = outcome("retention", "silver/subject", {"max_age_days": 5})
    assert result == "fail" and float(observed) > 9.9 and expected == "5"


def test_sql(write):
    write("silver/subject", "SELECT 'a' AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    assert outcome("sql", "silver/subject", {"sql": "SELECT 1 FROM silver_subject WHERE subject_pid = 'z'"}) == ("pass", "0", "0")
    assert outcome("sql", "silver/subject", {"sql": "SELECT 1 FROM silver_subject"}) == ("fail", "1", "0")


def test_generator_rejects_malformed_and_deeply_nested_sql(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="malformed"):
        checks.generate("t", "T", "sql", "silver/subject", {"sql": "SELECT 1 FROM t WHERE (a OR b"})
    nested = "SELECT 1 FROM t WHERE " + "(" * 40 + "a = 1" + ")" * 40
    with pytest.raises(ValueError, match="IN \\(...\\)"):
        checks.generate("t", "T", "sql", "silver/subject", {"sql": nested})
    ok = "SELECT 1 FROM t WHERE channel_idx IN (" + ", ".join(map(str, range(512))) + ")"
    assert len(checks.generate("t", "T", "sql", "silver/subject", {"sql": ok})) == 1
    with pytest.raises(ValueError, match="unknown check_kind"):
        checks.generate("t", "T", "regex", "silver/subject", {})


def test_gold_star_expands_to_every_gold_dataset_and_error_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    generated = checks.generate("g", "G", "no_direct_identifier", "gold/*", {"forbidden_columns": ["subject_src"]})
    assert [c.dataset for c in generated] == [d for d in db.DATASETS if d.startswith("gold/")]
    assert len({c.check_id for c in generated}) == len(generated)
    [bad] = checks.generate("g", "G", "sql", "silver/subject", {"sql": "SELECT 1 FROM no_such_view"})
    [row] = checks.run(db.connect(), [bad])
    assert (row["result"], row["observed"], row["expected"]) == ("error", None, None)
