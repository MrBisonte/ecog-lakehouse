import json

import numpy as np
import pytest

from pipeline import db, line_noise, publish, synth
from tests.conftest import CHANNELS, FILES, SECONDS


@pytest.fixture(scope="module")
def gold(built):
    return db.connect()


def test_ratio_is_null_under_10_s_and_near_one_for_a_pure_50_hz_tone():
    t = np.arange(10_000) / 1000
    assert line_noise.ratio(np.sin(2 * np.pi * 50 * t[:9_999]), 1000) is None
    assert line_noise.ratio(np.sin(2 * np.pi * 50 * t), 1000) > 0.99
    assert line_noise.ratio(np.sin(2 * np.pi * 10 * t), 1000) < 0.01


def test_channel_quality(gold):
    assert gold.execute("SELECT count(*) FROM gold_channel_quality").fetchone()[0] == FILES * CHANNELS
    assert gold.execute("SELECT sum(missing_samples) FROM gold_channel_quality").fetchone()[0] == (
        len(synth.SUBJECTS) * synth.NAN_BURST_SAMPLES
    )
    assert gold.execute(
        "SELECT count(*) FROM gold_channel_quality WHERE n_samples + missing_samples <> ?",
        [SECONDS * 1000],
    ).fetchone()[0] == 0
    assert gold.execute(
        "SELECT count(*) FROM gold_channel_quality WHERE line_noise_ratio IS NULL "
        "OR line_noise_ratio < 0 OR line_noise_ratio > 1 OR rms_uv <= 0 OR lid_decode(lid).layer <> 3"
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
    assert len(rows) == FILES
    assert set(rows) == {(1, CHANNELS, float(SECONDS), SECONDS // 2)}


def test_feature_window(gold):
    assert gold.execute("SELECT count(*) FROM gold_feature_window").fetchone()[0] == (
        FILES * CHANNELS * SECONDS
    )
    assert gold.execute(
        "SELECT count(*) FROM gold_feature_window WHERE window_start_ms % 1000 <> 0 "
        "OR sample_lo < window_start_ms OR sample_hi >= window_start_ms + 1000 "
        "OR p2p_uv < 0 OR std_uv < 0 OR lid_decode(lid).layer <> 3 "
        "OR lid_parent(lid) NOT IN (SELECT lid FROM silver_record)"
    ).fetchone()[0] == 0


def test_publish_writes_manifest_within_limits(built, tmp_path, monkeypatch):
    assert publish.main(["--out", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert {f["path"] for f in manifest["files"]} == {
        "gold/channel_quality/data_0.parquet",
        "gold/experiment_summary/data_0.parquet",
        "gold/feature_window/data_0.parquet",
    }
    assert all((tmp_path / f["path"]).stat().st_size == f["bytes"] for f in manifest["files"])
    monkeypatch.setattr(publish, "FILE_LIMIT", 1)
    assert publish.main(["--out", str(tmp_path)]) == 1
