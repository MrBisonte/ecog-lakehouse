import numpy as np
from scipy.io import loadmat

from pipeline import synth


def test_generate_shapes_and_one_nan_burst():
    f = synth.generate("fingerflex", "bb", seconds=2, channels=4)
    assert f["data"].shape == (2000, 4) and f["data"].dtype == np.float32
    assert int(np.isnan(f["data"]).sum()) == synth.NAN_BURST_SAMPLES
    assert f["stim"].shape == (2000,) and set(np.unique(f["stim"])) <= {0, 1, 2}
    assert f["locs"].shape == (4, 3)
    again = synth.generate("fingerflex", "bb", 2, 4)["data"]
    assert np.array_equal(again, f["data"], equal_nan=True)


def test_motor_basic_has_no_nan_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert synth.main(["--seconds", "1", "--channels", "3"]) == 0
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.mat"))
    assert written == sorted(
        f"raw/synthetic/{e}/{s}.mat" for e in synth.EXPERIMENTS for s in synth.SUBJECTS
    )
    m = loadmat(tmp_path / "raw/synthetic/motor_basic/aa.mat", simplify_cells=True)
    assert m["experiment"] == "motor_basic" and m["subject"] == "aa" and int(m["srate"]) == 1000
    assert not np.isnan(m["data"]).any()
    assert list(m["brain_area"][:2]) == ["precentral", "postcentral"]


def test_canary_mode_writes_only_the_canary_of_the_named_experiments(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert synth.main(["--canary", "faces_basic", "fingerflex", "unknown", "--seconds", "1", "--channels", "2"]) == 0
    written = sorted(p.relative_to(tmp_path / "raw" / "synthetic").as_posix() for p in tmp_path.rglob("*.mat"))
    assert written == ["faces_basic/canary.mat", "fingerflex/canary.mat"]
