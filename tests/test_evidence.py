import hashlib

from pipeline import checks, db


def evidence_files(root):
    return sorted((root / "gold" / "evidence").rglob("*.parquet"))


def test_every_governance_check_passes_on_the_built_layers(built):
    rows = db.connect().execute(
        "SELECT check_id, result, observed, expected FROM gold_evidence WHERE result <> 'pass'"
    ).fetchall()
    assert rows == []
    kinds = {r[0] for r in db.connect().execute("SELECT DISTINCT check_kind FROM gold_evidence").fetchall()}
    assert {"hash_match", "not_null", "no_direct_identifier", "row_count_min", "unique", "partition_layout", "sql"} <= kinds


def test_evidence_is_append_only_and_versions_repeat_for_identical_inputs(built):
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence_files(built)}
    assert len(before) >= 1
    assert checks.main([]) == 0
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence_files(built)}
    assert len(after) == len(before) + 1
    assert all(after[p] == digest for p, digest in before.items())
    con = db.connect()
    runs = con.execute("SELECT count(DISTINCT run_id) FROM gold_evidence").fetchone()[0]
    assert runs == len(after)
    drift = con.execute(
        "SELECT dataset, count(DISTINCT dataset_version) FROM gold_evidence "
        "WHERE dataset <> 'gold/evidence' GROUP BY 1 HAVING count(DISTINCT dataset_version) > 1"
    ).fetchall()
    assert drift == []
    assert con.execute(
        "SELECT count(*) FROM gold_evidence WHERE dataset_version IS NULL OR length(dataset_version) <> 64"
    ).fetchone()[0] == 0


def test_no_direct_identifier_fails_when_subject_src_leaks_into_silver(built, tmp_path, monkeypatch):
    leak = tmp_path / "silver" / "recording" / "experiment=fingerflex" / "subject_pid=p"
    leak.mkdir(parents=True)
    db.connect().execute(
        "COPY (SELECT *, 'aa' AS subject_src FROM silver_recording LIMIT 10) "
        f"TO '{(leak / 'data_0.parquet').as_posix()}' (FORMAT parquet)"
    )
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    gdpr = [
        c for c in checks.from_requirements()
        if c.check_kind == "no_direct_identifier" and c.dataset == "silver/recording"
    ]
    assert len(gdpr) == 1
    [row] = checks.run(db.connect(), gdpr)
    assert (row["result"], row["observed"], row["expected"]) == ("fail", "1", "0")
