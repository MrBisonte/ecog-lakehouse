"""fetch.py on a local file:// source: verify, skip, extract, and report a bad digest."""

import hashlib
import zipfile

from pipeline import fetch


def make_source(tmp_path):
    archive = tmp_path / "src" / "demo.zip"
    archive.parent.mkdir()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("demo/data/xx/xx_demo.mat", b"MATLAB 5.0 MAT-file, not really")
    body = archive.read_bytes()
    return {
        "experiment": "demo",
        "file": "demo.zip",
        "url": archive.as_uri(),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": str(len(body)),
    }


def test_fetch_downloads_verifies_extracts_then_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    row = make_source(tmp_path)
    assert fetch.fetch_row(row) is None
    raw = tmp_path / "data" / "raw" / "demo"
    assert (raw / "demo.zip").exists()
    assert (raw / "demo" / "data" / "xx" / "xx_demo.mat").exists()
    assert fetch.fetch_row(row) is None
    assert "present and verified" in capsys.readouterr().out


def test_fetch_reports_a_digest_mismatch_and_keeps_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    row = make_source(tmp_path)
    row["sha256"] = "0" * 64
    reason = fetch.fetch_row(row)
    assert reason is not None and "sha256" in reason
    assert (tmp_path / "data" / "raw" / "demo" / "demo.zip").exists()
    assert not list((tmp_path / "data" / "raw" / "demo").rglob("*.mat"))


def test_fetch_resumes_a_partial_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    row = make_source(tmp_path)
    target = tmp_path / "data" / "raw" / "demo" / "demo.zip"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\x00" * 10)  # a partial file the file:// scheme cannot resume
    assert fetch.fetch_row(row) is None, "a 200 answer restarts the file from byte 0"
    assert target.stat().st_size == int(row["bytes"])
