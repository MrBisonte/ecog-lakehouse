"""Copy Gold to docs/data/gold and write docs/data/manifest.json, within the limits of spec 9.

A file holding a canary record (radioactive bit, spec 12.5) is refused before anything is
copied, and so is a commit recorded in Gold that is not in the history of HEAD. Gold is copied
from DATA_DIR; fault files under docs/data/faults are listed as found. checks.json and lid.sql
let docs/index.html rerun the Gold checks in the browser, and summary.json holds the numbers it
paints before the engine loads, with the statement that produced them (spec 8).
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline import checks, db

FILE_LIMIT = 95 * 1024**2
TOTAL_LIMIT = 500 * 1024**2
# Check kinds whose SQL needs only the Gold views, so the browser page (spec 8) can rerun them
# over the published files. The others read DATA_DIR or the source files.
BROWSER_KINDS = {"not_null", "unique", "row_count_min", "no_direct_identifier", "sql"}
# The numbers the page paints before the engine loads, spec 8: one statement over the Gold
# views, published with its result so the page can run it again over the verified files.
SUMMARY_SQL = """\
WITH latest AS (SELECT * FROM gold_evidence WHERE run_id = (SELECT max(run_id) FROM gold_evidence))
SELECT (SELECT count(DISTINCT dataset) FROM latest WHERE dataset LIKE 'gold/%') AS gold_datasets,
       (SELECT sum(n_records)::BIGINT FROM gold_dataset_manifest WHERE layer = 1) AS bronze_rows,
       (SELECT n_records FROM gold_dataset_manifest WHERE dataset = 'silver/recording') AS samples,
       count(*) AS checks,
       count(*) FILTER (WHERE result = 'pass') AS pass,
       count(*) FILTER (WHERE result <> 'pass' AND severity = 'block') AS fail,
       count(*) FILTER (WHERE result <> 'pass' AND severity = 'flag') AS flag,
       strftime(min(ran_at), '%Y-%m-%d %H:%M:%S') AS ran_at,
       left(any_value(git_commit), 7) AS git_commit
FROM latest"""


def radioactive_rows(con, path: Path) -> int:
    """Rows of one Parquet file whose lid carries the radioactive bit, 0 when it has no lid."""
    columns = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path.as_posix()}')").fetchall()}
    if "lid" not in columns:
        return 0
    return con.execute(
        f"SELECT count(*) FROM read_parquet('{path.as_posix()}') "
        "WHERE lid IS NOT NULL AND lid_radioactive(lid_from_uuid(lid)) = 1"
    ).fetchone()[0]


def unknown_commits(con) -> list[str]:
    """Commits recorded in gold/evidence and gold/dataset_manifest that are neither HEAD nor an
    ancestor of it. The page shows the commit of every run, and each must open in the repository."""
    recorded = con.execute(
        "SELECT git_commit FROM gold_evidence UNION SELECT git_commit FROM gold_dataset_manifest"
    ).fetchall()
    return sorted(
        str(c) for (c,) in recorded
        # Recorded text is never passed to git unless it is a hash, so it cannot be read as an option.
        if not re.fullmatch(r"[0-9a-f]{7,40}", str(c))
        or subprocess.run(
            ["git", "-C", str(db.REPO), "merge-base", "--is-ancestor", c, "HEAD"],
            capture_output=True, check=False,
        ).returncode != 0
    )


def summary(con) -> dict:
    """SUMMARY_SQL and its one row, as summary.json carries them."""
    con.execute(SUMMARY_SQL)
    return {"sql": SUMMARY_SQL, "values": dict(zip([d[0] for d in con.description], con.fetchone()))}


def entry(rel: str, path: Path) -> dict:
    return {"path": rel, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def browser_checks() -> list[dict]:
    """The checks the page reruns: Gold datasets, kinds that need only the views and lid.sql."""
    return [
        {"check_id": c.check_id, "requirement_id": c.requirement_id, "framework": c.framework,
         "dataset": c.dataset, "check_kind": c.check_kind, "severity": c.severity,
         "clause": c.clause, "control": c.control, "sql": c.sql, "expected": c.expected,
         "compare": c.compare}
        for c in checks.from_requirements() + checks.from_contracts()
        if c.dataset.startswith("gold/") and c.check_kind in BROWSER_KINDS
    ]


def publish(out: Path) -> int:
    gold = db.data_dir() / "gold"
    sources = sorted(gold.rglob("*.parquet"))
    con = db.connect()
    leaks = {p.relative_to(db.data_dir()).as_posix(): radioactive_rows(con, p) for p in sources}
    if any(leaks.values()):
        print(f"publish: refused, canary records in {[p for p, n in leaks.items() if n]}")
        return 1
    if unknown := unknown_commits(con):
        print(
            f"publish: refused, commits not in the history of HEAD: {unknown}. Move the evidence "
            "runs that record them to DATA_DIR/quarantine/evidence; make gold rewrites the manifest"
        )
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
    (out / "summary.json").write_text(json.dumps(summary(con), indent=1) + "\n")
    files.append(entry("summary.json", out / "summary.json"))
    total = sum(f["bytes"] for f in files)
    over = [f["path"] for f in files if f["bytes"] > FILE_LIMIT]
    if over or total > TOTAL_LIMIT:
        print(f"publish: refused, over the limit: files {over}, total {total} bytes")
        return 1
    (out / "manifest.json").write_text(json.dumps({"files": files, "bytes": total}, indent=1) + "\n")
    (out / "checks.json").write_text(json.dumps(browser_checks(), indent=1) + "\n")
    shutil.copyfile(db.SQL / "lineage" / "lid_generated.sql", out / "lid.sql")
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
