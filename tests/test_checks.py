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


def outcome(kind, dataset, params, severity="block"):
    [check] = checks.generate("test", "T-1", kind, dataset, params, severity=severity)
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
        f"SELECT 'I1' AS ingest_id, '{tmp_path.as_posix()}' AS data_root, "
        "'raw/synthetic/x.bin' AS source_path_rel, 'u' AS source_url, "
        f"'{digest}' AS sha256, 14::BIGINT AS bytes, 1000 AS sample_rate_hz, 1::BIGINT AS rows_written, "
        "'t' AS tool, 'v' AS tool_version, 'd' AS duckdb_version, 'h' AS ingest_host, "
        "now()::TIMESTAMP AS ingested_at",
    )
    assert outcome("hash_match", "bronze/ingest_audit", {}) == ("pass", "0", "0")
    raw.write_bytes(b"tampered bytes")
    assert outcome("hash_match", "bronze/ingest_audit", {}) == ("fail", "1", "0")
    raw.unlink()
    assert outcome("hash_match", "bronze/ingest_audit", {}) == ("fail", "1", "0")


def test_hash_match_survives_a_moved_lakehouse(write, tmp_path, monkeypatch):
    """The row records where the file was; the check reads the digest, not the mount point."""
    raw = tmp_path / "raw" / "synthetic" / "x.bin"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"original bytes")
    digest = hashlib.sha256(b"original bytes").hexdigest()
    write(
        "bronze/ingest_audit",
        "SELECT 'I1' AS ingest_id, '/gone' AS data_root, "
        "'raw/synthetic/x.bin' AS source_path_rel, 'u' AS source_url, "
        f"'{digest}' AS sha256, 14::BIGINT AS bytes, 1000 AS sample_rate_hz, 1::BIGINT AS rows_written, "
        "'t' AS tool, 'v' AS tool_version, 'd' AS duckdb_version, 'h' AS ingest_host, "
        "now()::TIMESTAMP AS ingested_at",
    )
    moved = tmp_path.parent / (tmp_path.name + "-moved")
    tmp_path.rename(moved)
    monkeypatch.setenv("DATA_DIR", str(moved))
    assert outcome("hash_match", "bronze/ingest_audit", {}) == ("pass", "0", "0")


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


def test_every_check_carries_one_plain_sentence():
    """A reader who does not read SQL still learns what each check asserts."""
    from_csv = checks.from_requirements()
    from_yaml = checks.from_contracts()
    assert all(c.control for c in from_csv + from_yaml)
    # a requirement row's own words, verbatim, clause and all
    gdpr = next(c for c in from_csv if c.framework == "GDPR-Art9")
    assert gdpr.clause == "Processing of data concerning health is prohibited without safeguards"
    assert gdpr.control == (
        "pseudonymisation at the Silver boundary; no source identifier in Silver"
    )
    # a contract rule has no regulation behind it, so the sentence is built from the rule
    unique = next(c for c in from_yaml if c.check_kind == "unique")
    assert unique.clause is None
    assert unique.control.startswith("No two rows share the same ") and unique.control.endswith(".")
    assert next(c for c in from_yaml if c.check_kind == "not_null").control.startswith("Every row has")


def test_evidence_records_why_each_check_exists(built):
    con = db.connect()
    rows = con.execute(
        "SELECT count(*), count(control), count(clause) FROM gold_evidence "
        "WHERE run_id = (SELECT max(run_id) FROM gold_evidence)"
    ).fetchone()
    assert rows[0] == rows[1], "every evidence row says what it checked"
    assert 0 < rows[2] < rows[0], "only requirement rows carry a regulation clause"


def test_a_flag_check_names_the_records_and_reads_its_threshold_from_the_row(write):
    """A plausibility check reports which records it found, and never stops the build."""
    write("silver/subject",
          "SELECT unnest(['a', 'b', 'c']) AS subject_pid, now()::TIMESTAMP AS first_seen_at")
    above = {"sql": "SELECT subject_pid AS offender FROM silver_subject "
                    "WHERE subject_pid > '{{floor}}' ORDER BY 1", "floor": "a"}
    assert outcome("sql", "silver/subject", above, "flag") == ("fail", "2 of 3: b, c", "")
    clean = dict(above, floor="z")
    assert outcome("sql", "silver/subject", clean, "flag") == ("pass", "", "")
    with pytest.raises(ValueError, match="'block' or 'flag'"):
        checks.generate("t", "T", "sql", "silver/subject", {"sql": "SELECT 1"}, severity="warn")


def test_every_check_declares_whether_a_failure_blocks(built):
    con = db.connect()
    kinds = con.execute(
        "SELECT DISTINCT severity FROM gold_evidence "
        "WHERE run_id = (SELECT max(run_id) FROM gold_evidence) ORDER BY 1"
    ).fetchall()
    assert kinds and all(k[0] in ("block", "flag") for k in kinds)
    assert all(c.severity == "block" for c in checks.from_contracts()), "a contract rule blocks"
