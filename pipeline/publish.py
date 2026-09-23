"""Copy Gold to docs/data/gold and write docs/data/manifest.json, within the limits of spec 9.

A file holding a canary record (radioactive bit, spec 12.5) is refused before anything is
copied. Gold is copied from DATA_DIR; fault files under docs/data/faults are listed as found.
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


def radioactive_rows(con, path: Path) -> int:
    """Rows of one Parquet file whose lid carries the canary bit, 0 when it has no lid."""
    columns = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path.as_posix()}')").fetchall()}
    if "lid" not in columns:
        return 0
    return con.execute(
        f"SELECT count(*) FROM read_parquet('{path.as_posix()}') "
        "WHERE lid IS NOT NULL AND lid_radioactive(lid_from_uuid(lid)) = 1"
    ).fetchone()[0]


def entry(rel: str, path: Path) -> dict:
    return {"path": rel, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def publish(out: Path) -> int:
    gold = db.data_dir() / "gold"
    sources = sorted(gold.rglob("*.parquet"))
    con = db.connect()
    leaks = {p.relative_to(db.data_dir()).as_posix(): radioactive_rows(con, p) for p in sources}
    if any(leaks.values()):
        print(f"publish: refused, canary records in {[p for p, n in leaks.items() if n]}")
        return 1
    shutil.rmtree(out / "gold", ignore_errors=True)
    files = []
    for path in sources:
        rel = path.relative_to(db.data_dir())
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, out / rel)
        files.append(entry(rel.as_posix(), path))
    # Fault files (spec 6) are written under docs/data/faults by faults/*/bench.sh, not copied
    # from DATA_DIR; they count against the same limits and enter the manifest when present.
    for path in sorted((out / "faults").rglob("*.parquet")):
        files.append(entry(path.relative_to(out).as_posix(), path))
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
    parser.add_argument(
        "--out",
        default=str(Path.cwd() / "docs" / "data"),
        help="where to publish, default docs/data under the working directory. An editable "
        "install can point at another checkout, which must not be written to",
    )
    args = parser.parse_args(argv)
    return publish(Path(args.out))


if __name__ == "__main__":
    sys.exit(main())
