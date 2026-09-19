"""Governance as code, spec 5: every requirements.csv row and every contract rule becomes one
SQL check per dataset, each run leaves one gold/evidence row, evidence is append-only.

A check is a rendered template from sql/checks/<kind>.sql that returns one `observed` value.
The generator refuses SQL that does not parse and predicates nested deeper than MAX_NESTING.
"""

import csv
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch

import duckdb
import yaml

from pipeline import db
from pipeline.lid import ulid

REQUIREMENTS = db.REPO / "governance" / "requirements.csv"
CONTRACTS = db.REPO / "contracts"
MAX_NESTING = 32

# How observed must relate to expected for a pass.
COMPARE = {
    "not_null": "eq",
    "unique": "eq",
    "row_count_min": "ge",
    "no_direct_identifier": "eq",
    "hash_match": "eq",
    "partition_layout": "eq",
    "retention": "le",
    "sql": "eq",
}


@dataclass
class Check:
    check_id: str
    requirement_id: str
    framework: str
    dataset: str
    check_kind: str
    sql: str
    expected: str
    compare: str


def oldest_age_days(dataset: str) -> float:
    files = list((db.data_dir() / dataset).rglob("*.parquet"))
    return (time.time() - min(p.stat().st_mtime for p in files)) / 86400 if files else 0.0


def template_values(kind: str, dataset: str, params: dict):
    """Placeholder values for the kind's template, and the expected value."""
    values = {
        "view": db.view_name(dataset),
        "dataset": dataset,
        "data_dir": db.data_dir().as_posix(),
    }
    expected = 0
    match kind:
        case "not_null":
            values["column"] = params["column"]
        case "unique":
            values["columns"] = ", ".join(params["columns"])
        case "row_count_min":
            expected = params["min"]
        case "no_direct_identifier":
            values["forbidden_columns"] = ", ".join(f"'{c}'" for c in params["forbidden_columns"])
        case "hash_match":
            pass
        case "partition_layout":
            values["max_rows_per_row_group"] = params["max_rows_per_row_group"]
            values["min_row_groups"] = params["min_row_groups"]
        case "retention":
            values["oldest_age_days"] = round(oldest_age_days(dataset), 3)
            expected = params["max_age_days"]
        case "sql":
            values["query"] = params["sql"]
        case _:
            raise ValueError(f"unknown check_kind '{kind}', the kinds are in doc/spec.md section 5.2")
    return values, expected


def validate(sql: str) -> str:
    """Reject SQL that does not parse, and nesting a naive generator produces (fault G)."""
    report = json.loads(duckdb.connect().execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    if report.get("error"):
        raise ValueError(
            f"generated SQL is malformed: {report['error_message']} at position "
            f"{report.get('position')}: {sql[:200]}"
        )
    depth = deepest = 0
    for ch in sql:
        depth += (ch == "(") - (ch == ")")
        deepest = max(deepest, depth)
    if deepest > MAX_NESTING:
        raise ValueError(
            f"generated SQL nests {deepest} levels of parentheses, "
            "emit IN (...) or a join against a VALUES list instead"
        )
    return sql


def generate(framework, requirement_id, check_kind, dataset, params) -> list[Check]:
    """One check per dataset matching the pattern; `gold/*` expands to every Gold dataset."""
    names = [d for d in db.DATASETS if fnmatch(d, dataset)] or [dataset]
    checks = []
    for name in names:
        values, expected = template_values(check_kind, name, params)
        template = (db.SQL / "checks" / f"{check_kind}.sql").read_text(encoding="utf-8")
        sql = validate(db.render(template, **values))
        detail = [str(v) for v in params.values()]
        check_id = "/".join([requirement_id, check_kind, name, *detail])
        checks.append(
            Check(check_id, requirement_id, framework, name, check_kind, sql, str(expected),
                  COMPARE[check_kind])
        )
    return checks


def from_requirements(path=REQUIREMENTS) -> list[Check]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [
        c
        for row in rows
        for c in generate(
            row["framework"], row["requirement_id"], row["check_kind"], row["dataset"],
            json.loads(row["params"]),
        )
    ]


def from_contracts(folder=CONTRACTS) -> list[Check]:
    """required and unique properties, and every ibrain quality rule, become checks."""
    checks = []
    for path in sorted(folder.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        [obj] = doc["schema"]
        rules = []
        for prop in obj["properties"]:
            if prop.get("required"):
                rules.append(("not_null", {"column": prop["name"]}))
            if prop.get("unique"):
                rules.append(("unique", {"columns": [prop["name"]]}))
        for rule in obj.get("quality", []):
            if rule.get("engine") == "ibrain":
                rules.append((rule["implementation"]["check_kind"], rule["implementation"]["params"]))
        for kind, params in rules:
            checks += generate("contract", doc["id"], kind, doc["name"], params)
    return checks


def dataset_version(dataset: str) -> str:
    """sha256 of the sorted list of the dataset's Parquet file digests."""
    files = (db.data_dir() / dataset).rglob("*.parquet")
    digests = sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in files)
    return hashlib.sha256("\n".join(digests).encode()).hexdigest()


def passes(compare: str, observed: str, expected: str) -> bool:
    o, e = float(observed), float(expected)
    return {"eq": o == e, "ge": o >= e, "le": o <= e}[compare]


def run(con, checks: list[Check]) -> list[dict]:
    """Run every check, append one evidence file for this run, return the evidence rows."""
    run_id = ulid()
    ran_at = datetime.now(UTC).replace(tzinfo=None)
    versions = {}
    rows = []
    for c in checks:
        version = versions.setdefault(c.dataset, dataset_version(c.dataset))
        try:
            observed = str(con.execute(c.sql).fetchone()[0])
            expected = c.expected
            result = "pass" if passes(c.compare, observed, expected) else "fail"
        except duckdb.Error as e:
            print(f"checks: error in {c.check_id}: {str(e).splitlines()[0]}")
            result, observed, expected = "error", None, None
        rows.append(
            {
                "run_id": run_id,
                "check_id": c.check_id,
                "requirement_id": c.requirement_id,
                "framework": c.framework,
                "dataset": c.dataset,
                "dataset_version": version,
                "check_kind": c.check_kind,
                "result": result,
                "observed": observed,
                "expected": expected,
                "ran_at": ran_at,
                "engine_version": duckdb.__version__,
                "git_commit": db.git_commit(),
                "lid": None,
            }
        )
    target = db.data_dir() / "gold" / "evidence" / f"run_id={run_id}"
    target.mkdir(parents=True)
    con.execute(f"CREATE OR REPLACE TEMP TABLE evidence_run ({db.columns('gold/evidence')})")
    con.executemany(
        f"INSERT INTO evidence_run VALUES ({', '.join('?' * len(rows[0]))})",
        [tuple(r.values()) for r in rows],
    )
    con.execute(f"COPY evidence_run TO '{(target / 'data_0.parquet').as_posix()}' (FORMAT parquet)")
    db.views(con)
    return rows


def main(argv=None) -> int:
    con = db.connect()
    rows = run(con, from_requirements() + from_contracts())
    for r in rows:
        if r["result"] != "pass":
            print(f"checks: {r['result']} {r['check_id']} observed {r['observed']} expected {r['expected']}")
    counts = {k: sum(r["result"] == k for r in rows) for k in ("pass", "fail", "error")}
    print(f"checks: run {rows[0]['run_id']}, {counts}")
    return 0 if counts["fail"] == 0 and counts["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
