"""Fault D plant, spec 6: download every published Parquet file one at a time with urllib into
a temporary directory, then count the rows. The synchronous loop a first script always is.

    python faults/d/plant.py <base_url>

Prints the row count. The file list is docs/data/manifest.json under the same base URL.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

import duckdb


def main(base_url: str) -> int:
    manifest = json.load(urlopen(f"{base_url}/manifest.json", timeout=60))
    parquet = [f["path"] for f in manifest["files"] if f["path"].endswith(".parquet")]
    tmp = Path(tempfile.mkdtemp(prefix="fault_d_"))
    try:
        for rel in parquet:
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with urlopen(f"{base_url}/{rel}", timeout=60) as response, target.open("wb") as f:
                shutil.copyfileobj(response, f)
        files = [str(tmp / rel) for rel in parquet]
        rows = sum(duckdb.sql(f"SELECT count(*) FROM read_parquet('{f}')").fetchone()[0] for f in files)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
