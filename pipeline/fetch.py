"""Download every row of governance/sources.csv into DATA_DIR/raw/<experiment>/, spec 7.

A file already present with the recorded size and sha256 is skipped. A partial file is
resumed with a Range request. A verified zip is extracted next to itself once, when the
experiment directory holds no `.mat` yet. A row that fails is printed and the next row
runs; the exit code is the number of failed rows.
"""

import csv
import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from pipeline import db

SOURCES = db.REPO / "governance" / "sources.csv"


def verified(path: Path, row: dict) -> bool:
    return path.exists() and path.stat().st_size == int(row["bytes"]) and db.sha256(path) == row["sha256"]


def download(url: str, target: Path):
    """Fetch url to target, appending to a partial file when the server honours Range."""
    have = target.stat().st_size if target.exists() else 0
    request = Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urlopen(request, timeout=120) as response:
        resume = have > 0 and response.status == 206
        with target.open("ab" if resume else "wb") as f:
            shutil.copyfileobj(response, f, 1 << 20)


def extract(archive: Path):
    """Unpack a zip beside itself, once: skipped when a .mat already sits in the directory."""
    if any(archive.parent.rglob("*.mat")):
        return
    with zipfile.ZipFile(archive) as z:
        z.extractall(archive.parent)
    print(f"fetch: extracted {archive.name}")


def fetch_row(row: dict) -> str | None:
    """Download, verify and extract one row. Returns the failure reason, None on success."""
    target = db.data_dir() / "raw" / row["experiment"] / row["file"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if verified(target, row):
        print(f"fetch: skip {target}, present and verified")
    else:
        print(f"fetch: {row['url']}")
        try:
            download(row["url"], target)
        except OSError as e:
            return f"{row['file']}: download failed, {e}"
        if not verified(target, row):
            return f"{row['file']}: sha256 or size differs from sources.csv, file kept for resume"
    if target.suffix == ".zip":
        extract(target)
    return None


def main(argv=None) -> int:
    with SOURCES.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    failures = [reason for reason in (fetch_row(r) for r in rows) if reason]
    for reason in failures:
        print(f"fetch: FAILED {reason}")
    print(f"fetch: {len(rows) - len(failures)} of {len(rows)} files verified")
    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
