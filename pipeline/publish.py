"""Copy Gold to docs/data/gold and write docs/data/manifest.json, within the limits of spec 9.

Phase 0 publishes Gold only; fault files and checks.json arrive with the site.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from pipeline import db

FILE_LIMIT = 95 * 1024**2
TOTAL_LIMIT = 500 * 1024**2


def publish(out) -> int:
    gold = db.data_dir() / "gold"
    shutil.rmtree(out / "gold", ignore_errors=True)
    files = []
    for path in sorted(gold.rglob("*.parquet")):
        rel = path.relative_to(db.data_dir())
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, out / rel)
        files.append(
            {
                "path": rel.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    total = sum(f["bytes"] for f in files)
    over = [f["path"] for f in files if f["bytes"] > FILE_LIMIT]
    if over or total > TOTAL_LIMIT:
        print(f"publish: refused, over the limit: files {over}, total {total} bytes")
        return 1
    (out / "manifest.json").write_text(json.dumps({"files": files, "bytes": total}, indent=1) + "\n")
    print(f"publish: {len(files)} files, {total} bytes, manifest at {out / 'manifest.json'}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(db.REPO / "docs" / "data"))
    args = parser.parse_args(argv)
    return publish(Path(args.out))


if __name__ == "__main__":
    sys.exit(main())
