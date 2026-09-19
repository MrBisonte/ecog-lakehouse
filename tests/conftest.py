"""One small synthetic build per test session, in a temporary DATA_DIR."""

import pytest

from pipeline import run, synth

SECONDS = 30
CHANNELS = 16
FILES = len(synth.SUBJECTS) * len(synth.CUE_CODES)


@pytest.fixture(scope="session")
def data_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("ecog-lakehouse")
    patch = pytest.MonkeyPatch()
    patch.setenv("DATA_DIR", str(root))
    yield root
    patch.undo()


@pytest.fixture(scope="session")
def built(data_root):
    """Bronze, Silver and Gold from the small synthetic set, plus one directory without adapter."""
    synth.main(["--seconds", str(SECONDS), "--channels", str(CHANNELS)])
    (data_root / "raw" / "mystery").mkdir()
    (data_root / "raw" / "mystery" / "x.mat").write_bytes(b"not a mat file")
    for layer in ("bronze", "silver", "gold"):
        assert run.main([layer]) == 0
    return data_root
