import json

import duckdb
import numpy as np
import pytest

from pipeline import checks, db, line_noise, publish, synth
from tests.conftest import CHANNELS, MART_FILES, SECONDS


@pytest.fixture(scope="module")
def gold(built):
    return db.connect()


def test_ratio_is_null_under_10_s_and_near_one_for_a_pure_50_hz_tone():
    t = np.arange(10_000) / 1000
    assert line_noise.ratio(np.sin(2 * np.pi * 50 * t[:9_999]), 1000) is None
    assert line_noise.ratio(np.sin(2 * np.pi * 50 * t), 1000) > 0.99
    assert line_noise.ratio(np.sin(2 * np.pi * 10 * t), 1000) < 0.01


def test_channel_quality(gold):
    assert gold.execute("SELECT count(*) FROM gold_channel_quality").fetchone()[0] == MART_FILES * CHANNELS
    assert gold.execute("SELECT sum(missing_samples) FROM gold_channel_quality").fetchone()[0] == (
        (len(synth.SUBJECTS) - 1) * synth.NAN_BURST_SAMPLES
    )
    assert gold.execute(
        "SELECT count(*) FROM gold_channel_quality WHERE n_samples + missing_samples <> ?",
        [SECONDS * 1000],
    ).fetchone()[0] == 0
    assert gold.execute(
        "SELECT count(*) FROM gold_channel_quality WHERE line_noise_ratio IS NULL "
        "OR line_noise_ratio < 0 OR line_noise_ratio > 1 OR rms_uv <= 0 OR lid_layer(lid_from_uuid(lid)) <> 3"
    ).fetchone()[0] == 0
    noisy, clean = gold.execute(
        "SELECT min(line_noise_ratio) FILTER (WHERE channel_idx % 4 = 0), "
        "max(line_noise_ratio) FILTER (WHERE channel_idx % 4 <> 0) FROM gold_channel_quality"
    ).fetchone()
    assert noisy > clean, "channels with injected 50 Hz must rank above the others"


def test_experiment_summary(gold):
    rows = gold.execute(
        "SELECT n_runs, n_channels, duration_s, n_events FROM gold_experiment_summary"
    ).fetchall()
    assert len(rows) == MART_FILES
    assert set(rows) == {(1, CHANNELS, float(SECONDS), SECONDS // 2)}


def test_feature_window(gold):
    assert gold.execute("SELECT count(*) FROM gold_feature_window").fetchone()[0] == (
        MART_FILES * CHANNELS * SECONDS
    )
    assert gold.execute(
        "SELECT count(*) FROM gold_feature_window WHERE window_start_ms % 1000 <> 0 "
        "OR sample_lo < window_start_ms OR sample_hi >= window_start_ms + 1000 "
        "OR p2p_uv < 0 OR std_uv < 0 OR lid_layer(lid_from_uuid(lid)) <> 3 "
        "OR lid_parent(lid) NOT IN (SELECT lid FROM silver_record)"
    ).fetchone()[0] == 0


def test_no_canary_record_reaches_a_gold_mart(gold):
    for view in ("gold_channel_quality", "gold_feature_window"):
        assert gold.execute(
            f"SELECT count(*) FROM {view} WHERE lid_radioactive(lid_from_uuid(lid)) = 1"
        ).fetchone()[0] == 0, view
    canary = gold.execute(
        "SELECT DISTINCT subject_pid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 1"
    ).fetchall()
    assert len(canary) == 1
    assert gold.execute(
        "SELECT count(*) FROM gold_experiment_summary WHERE subject_pid = ?", [canary[0][0]]
    ).fetchone()[0] == 0


def test_dataset_manifest_has_one_row_per_dataset_of_the_build(gold, built):
    rows = gold.execute(
        "SELECT dataset, layer, lid_lo, lid_hi, n_records, file_digests, dataset_version "
        "FROM gold_dataset_manifest ORDER BY dataset"
    ).fetchall()
    present = sorted(
        d for d in db.DATASETS
        if d not in ("gold/dataset_manifest", "gold/evidence") and any((built / d).rglob("*.parquet"))
    )
    assert [r[0] for r in rows] == present, "written at Gold time, before the first checks run"
    for dataset, layer, lo, hi, n, digests, version in rows:
        assert layer == {"bronze": 1, "silver": 2, "gold": 3}[dataset.split("/")[0]]
        assert n == gold.execute(f"SELECT count(*) FROM {db.view_name(dataset)}").fetchone()[0]
        assert len(version) == 64 and len(digests) >= 1 and all(len(d) == 64 for d in digests)
        if lo is not None:
            assert str(lo) <= str(hi)
    silver_version = gold.execute(
        "SELECT dataset_version FROM gold_dataset_manifest WHERE dataset = 'silver/recording'"
    ).fetchone()[0]
    assert silver_version == db.dataset_version("silver/recording")


def test_publish_writes_manifest_within_limits(built, tmp_path, monkeypatch):
    assert publish.main(["--out", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert {f["path"].split("/")[1] for f in manifest["files"]} == {
        "channel_quality", "experiment_summary", "feature_window", "evidence", "dataset_manifest",
    }
    assert all(f["path"].startswith("gold/") and len(f["sha256"]) == 64 for f in manifest["files"])
    monkeypatch.setattr(publish, "FILE_LIMIT", 1)
    assert publish.main(["--out", str(tmp_path)]) == 1


def test_publish_refuses_a_canary_record(built, tmp_path, monkeypatch):
    leak = tmp_path / "data" / "gold" / "channel_quality"
    leak.mkdir(parents=True)
    canary = db.connect().execute(
        "SELECT lid FROM silver_record WHERE lid_radioactive(lid_from_uuid(lid)) = 1 LIMIT 1"
    ).fetchone()[0]
    duckdb.connect().execute(
        f"COPY (SELECT '{canary}'::UUID AS lid, 1 AS n) TO '{(leak / 'data_0.parquet').as_posix()}' (FORMAT parquet)"
    )
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    out = tmp_path / "out"
    assert publish.main(["--out", str(out)]) == 1
    assert not (out / "manifest.json").exists()


def test_dataset_version_in_manifest_equals_the_one_evidence_recorded(gold, built):
    rows = gold.execute(
        "SELECT m.dataset, m.dataset_version, e.dataset_version "
        "FROM gold_dataset_manifest m "
        "JOIN (SELECT DISTINCT dataset, dataset_version FROM gold_evidence "
        "      WHERE run_id = (SELECT max(run_id) FROM gold_evidence)) e USING (dataset) "
        "ORDER BY 1"
    ).fetchall()
    assert len(rows) >= 3, "Silver and Gold datasets are checked and listed in the manifest"
    assert all(manifest == evidence for _, manifest, evidence in rows), rows


def test_published_copy_is_checked_for_canary_lids(gold, built):
    result = gold.execute(
        "SELECT result FROM gold_evidence WHERE dataset = 'docs/data' AND check_kind = 'sql'"
    ).fetchall()
    assert result and all(r[0] == "pass" for r in result)


def test_publish_default_out_follows_the_working_directory(built, tmp_path, monkeypatch):
    """An editable install points at the checkout it was installed from, so a verifier running
    from a clone must not publish into that checkout."""
    install = tmp_path / "install"
    (install / "docs" / "data").mkdir(parents=True)
    monkeypatch.setattr(db, "REPO", install)
    monkeypatch.chdir(tmp_path)
    assert publish.main([]) == 0
    assert json.loads((tmp_path / "docs" / "data" / "manifest.json").read_text())["files"]
    assert list((install / "docs" / "data").iterdir()) == []


def test_published_checks_rerun_over_the_published_files_alone(built, tmp_path):
    """What docs/index.html does: views over the published Parquet, lid.sql, then checks.json."""
    assert publish.main(["--out", str(tmp_path)]) == 0
    browser = json.loads((tmp_path / "checks.json").read_text())
    assert {c["dataset"] for c in browser} >= {"gold/channel_quality", "gold/feature_window"}
    assert all(c["dataset"].startswith("gold/") for c in browser)
    con = duckdb.connect()
    for dataset in {c["dataset"] for c in browser}:
        con.execute(
            f"CREATE VIEW {db.view_name(dataset)} AS SELECT * FROM read_parquet("
            f"'{(tmp_path / dataset).as_posix()}/**/*.parquet', hive_partitioning = true)"
        )
    con.execute((tmp_path / "lid.sql").read_text())
    for c in browser:
        observed = con.execute(c["sql"]).fetchone()[0]
        assert checks.passes(c["compare"], str(observed), c["expected"]), c["check_id"]
