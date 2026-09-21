"""Stanford adapters on tiny files in the library's layout, and the MATLAB v7.3 guard."""

import numpy as np
from scipy.io import savemat

from pipeline import convert_mat, db


def write_fingerflex(root, code="bp", samples=3000, channels=4):
    """data/<code>/<code>_fingerflex.mat with the README's variables, plus the unused stim file."""
    folder = root / "fingerflex" / "data" / code
    folder.mkdir(parents=True)
    cue = np.zeros((samples, 1))
    cue[1000:2000] = 3  # one middle finger cue
    savemat(folder / f"{code}_fingerflex.mat", {
        "data": np.arange(samples * channels, dtype=np.int32).reshape(samples, channels),
        "cue": cue,
        "locs": np.ones((channels, 3)) * 2.5,
        "elec_regions": np.array([[1], [4], [0], [8]]),
        "flex": np.zeros((samples, 5)),
    })
    savemat(folder / f"{code}_stim.mat", {"stim": cue})
    return folder / f"{code}_fingerflex.mat"


def test_read_fingerflex_maps_the_readme_fields(tmp_path):
    src = convert_mat.read_fingerflex(write_fingerflex(tmp_path))
    assert (src.experiment, src.subject_src, src.run, src.sample_rate_hz) == ("fingerflex", "bp", 1, 1000)
    assert src.data.shape == (3000, 4) and src.data.dtype == np.float32
    assert src.stim.shape == (3000,) and src.stim[1500] == 3 and src.stim[0] == 0
    assert src.brain_area == ["dorsal M1", "ventral sensorimotor", None, "temporal"]
    assert src.labels[3] == "middle"
    assert src.source_url.endswith("/fingerflex.zip")


def write_motor_basic(root, code="bp", samples=3000, channels=3):
    """data/<code>_mot_t_h.mat and locs/<code>_electrodes.mat, the README's variables."""
    (root / "motor_basic" / "data").mkdir(parents=True)
    (root / "motor_basic" / "locs").mkdir()
    stim = np.zeros((samples, 1))
    stim[500:1500] = 12
    stim[2000:2500] = 11
    savemat(root / "motor_basic" / "data" / f"{code}_mot_t_h.mat", {
        "data": np.arange(samples * channels, dtype=np.int16).reshape(samples, channels),
        "stim": stim,
    })
    savemat(root / "motor_basic" / "locs" / f"{code}_electrodes.mat", {"electrodes": np.ones((channels, 3))})
    return root / "motor_basic" / "data" / f"{code}_mot_t_h.mat"


def test_read_motor_basic_maps_the_readme_fields(tmp_path):
    src = convert_mat.read_motor_basic(write_motor_basic(tmp_path))
    assert (src.experiment, src.subject_src, src.run, src.sample_rate_hz) == ("motor_basic", "bp", 1, 1000)
    assert src.data.shape == (3000, 3) and src.data.dtype == np.float32
    assert src.stim[1000] == 12 and src.stim[2200] == 11 and src.stim[0] == 0
    assert src.locs.shape == (3, 3) and src.brain_area is None
    assert src.labels == {11: "tongue", 12: "hand"}
    _, pattern = convert_mat.ADAPTERS["motor_basic"]
    assert [p.name for p in tmp_path.glob(pattern)] == ["bp_mot_t_h.mat"]


def write_faces_basic(root, code="aa", samples=3000, channels=3):
    """data/<code>/<code>_faceshouses.mat and locs/<code>_xslocs.mat, the README's variables."""
    (root / "faces_basic" / "data" / code).mkdir(parents=True)
    (root / "faces_basic" / "locs").mkdir()
    stim = np.zeros((samples, 1))
    stim[400:800] = 7  # a house
    stim[800:1200] = 101  # interstimulus interval, not an event
    stim[1200:1600] = 63  # a face
    savemat(root / "faces_basic" / "data" / code / f"{code}_faceshouses.mat", {
        "data": np.arange(samples * channels, dtype=np.float64).reshape(samples, channels),
        "stim": stim,
        "srate": 1000,
    })
    savemat(root / "faces_basic" / "locs" / f"{code}_xslocs.mat", {
        "elcode": np.array([[5], [20], [11]]), "locs": np.ones((channels, 3)), "clims": np.array([0, 1]),
    })
    return root / "faces_basic" / "data" / code / f"{code}_faceshouses.mat"


def test_read_faces_basic_maps_the_readme_fields(tmp_path):
    src = convert_mat.read_faces_basic(write_faces_basic(tmp_path))
    assert (src.experiment, src.subject_src, src.run, src.sample_rate_hz) == ("faces_basic", "aa", 1, 1000)
    assert src.data.dtype == np.float32 and src.locs is None
    assert src.stim[600] == 7 and src.stim[1000] == 0 and src.stim[1400] == 63
    assert src.brain_area == ["fusiform gyrus", None, "occipital pole"]
    assert src.labels[7] == "house" and src.labels[63] == "face" and 101 not in src.labels
    _, pattern = convert_mat.ADAPTERS["faces_basic"]
    assert [p.name for p in tmp_path.glob(pattern)] == ["aa_faceshouses.mat"]


def test_faces_basic_converts_with_null_locations(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    path = write_faces_basic(tmp_path)
    con = db.connect()
    assert convert_mat.convert(con, path, convert_mat.read_faces_basic) == 9000
    electrodes = con.execute(
        "SELECT channel_idx, x_mm, y_mm, z_mm, brain_area FROM bronze_electrode ORDER BY 1"
    ).fetchall()
    assert electrodes == [(0, None, None, None, "fusiform gyrus"), (1, None, None, None, None),
                          (2, None, None, None, "occipital pole")]
    events = con.execute("SELECT sample_idx, event_code, event_label FROM bronze_event ORDER BY 1").fetchall()
    assert events == [(400, 7, "house"), (1200, 63, "face")]


def test_fingerflex_glob_takes_only_the_data_files(tmp_path):
    write_fingerflex(tmp_path)
    _, pattern = convert_mat.ADAPTERS["fingerflex"]
    assert [p.name for p in tmp_path.glob(pattern)] == ["bp_fingerflex.mat"]


def test_v73_file_is_skipped_with_a_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    path = tmp_path / "hd_fingerflex.mat"
    path.write_bytes(b"MATLAB 7.3 MAT-file, Platform: GLNXA64".ljust(128) + b"\x89HDF\r\n\x1a\n")
    con = db.connect()
    assert convert_mat.convert(con, path, convert_mat.read_fingerflex) == 0
    assert "ADR-0005" in capsys.readouterr().out
    assert con.execute("SELECT count(*) FROM bronze_ingest_audit").fetchone()[0] == 0
