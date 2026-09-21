"""The planted faults that have pure logic: G's generated SQL against the generator's guard,
and F's flaky proxy. A and D are benchmarks over published files, run by make bench."""

import importlib.util
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from pipeline import checks, db

FAULTS = db.REPO / "faults"


def load(path: Path, name: str, argv: list[str]):
    """Import a fault script as a module with the argv it expects."""
    sys.argv = [str(path), *argv]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fault_g_plant_is_refused_by_the_generator_and_the_fix_is_not(tmp_path):
    subprocess.run([sys.executable, str(FAULTS / "g" / "plant.py"), str(tmp_path)], check=True)
    nested = (tmp_path / "nested.sql").read_text()
    malformed = (tmp_path / "malformed.sql").read_text()
    fixed = (tmp_path / "fixed.sql").read_text()
    assert nested.count("(") == 512 and "channel_idx = 511" in nested
    with pytest.raises(ValueError, match="nests"):
        checks.validate(nested)
    with pytest.raises(ValueError, match="malformed"):
        checks.validate(malformed)
    assert checks.validate(fixed) == fixed
    assert "channel_idx IN (0, 1, 2" in fixed


@pytest.fixture
def served(tmp_path):
    """A file served by faults/serve.py on a free port, range requests honoured as on Pages."""
    (tmp_path / "file.bin").write_bytes(bytes(range(256)) * 64)
    ranged_handler = load(FAULTS / "serve.py", "serve", [str(tmp_path)]).Ranged
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(ranged_handler, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def proxy(base_url: str, fraction: float) -> str:
    module = load(FAULTS / "f" / "flaky_proxy.py", f"flaky_{fraction}", [base_url, "0", str(fraction)])
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Flaky)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.1)
    return f"http://127.0.0.1:{server.server_port}"


def ranged(url: str) -> int:
    try:
        with urlopen(Request(url, headers={"Range": "bytes=0-15"}), timeout=5) as r:
            return r.status
    except HTTPError as e:
        return e.code


def test_fault_f_proxy_fails_the_configured_fraction_of_range_requests(served):
    always = proxy(served, 1.0)
    assert [ranged(f"{always}/file.bin") for _ in range(3)] == [503, 503, 503]
    never = proxy(served, 0.0)
    assert [ranged(f"{never}/file.bin") for _ in range(3)] == [206, 206, 206]
    tenth = proxy(served, 0.1)
    assert [ranged(f"{tenth}/file.bin") for _ in range(10)].count(503) == 1
    with urlopen(f"{never}/file.bin", timeout=5) as r:  # a plain GET is never failed
        assert r.status == 200 and len(r.read()) == 256 * 64
