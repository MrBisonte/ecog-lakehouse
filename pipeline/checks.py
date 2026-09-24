"""Governance as code, spec 5: every requirements.csv row and every contract rule becomes one
SQL check per dataset, each run leaves one gold/evidence row, evidence is append-only.

A check is a rendered template from sql/checks/<kind>.sql that returns one `observed` value.
The generator refuses SQL that does not parse and predicates nested deeper than MAX_NESTING.
"""

import csv
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


# One plain sentence per check kind, for a reader who does not read SQL. A requirement row
# carries its own `control` text; a contract rule has none, so the sentence is built from the
# rule itself. Neither is ever typed per check.
CONTROL = {
    "not_null": lambda p: f"Every row has a value for {p['column']}.",
    "unique": lambda p: "No two rows share the same " + " and ".join(p["columns"]) + ".",
    "row_count_min": lambda p: (
        "The dataset is not empty." if p["min"] == 1 else f"At least {p['min']} rows are present."
    ),
    "no_direct_identifier": lambda p: (
        "No column here is named " + " or ".join(p["forbidden_columns"]) + "."
    ),
    "hash_match": lambda p: "Every ingested file still matches the digest recorded for it.",
    "partition_layout": lambda p: (
        f"Files keep row groups of at most {p['max_rows_per_row_group']:,} rows, so a reader "
        "can fetch part of a file instead of all of it."
    ),
    "retention": lambda p: f"No file here is older than {p['max_age_days']} days.",
    "sql": lambda p: "A rule of this dataset, written as a query that must return nothing.",
}


@dataclass
class Check:
    check_id: str
    requirement_id: str
    framework: str
    dataset: str
    check_kind: str
    severity: str
    clause: str | None
    control: str
    sql: str
    expected: str
    compare: str


def oldest_age_days(dataset: str) -> float:
    files = list((db.data_dir() / dataset).rglob("*.parquet"))
    return (time.time() - min(p.stat().st_mtime for p in files)) / 86400 if files else 0.0


def template_name(kind: str, severity: str) -> str:
    """A flag check reports the records it found, so `sql` at severity flag has its own template."""
    return "sql_flag" if kind == "sql" and severity == "flag" else kind


def template_values(kind: str, dataset: str, params: dict, severity: str = "block"):
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
            # Thresholds live in the requirement row beside the query, never in this file.
            values["query"] = db.render(params["sql"], **{k: v for k, v in params.items()
                                                          if k != "sql"})
            if severity == "flag":
                expected = "no records"
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


def generate(framework, requirement_id, check_kind, dataset, params, clause=None,
             control=None, severity="block") -> list[Check]:
    """One check per dataset matching the pattern; `gold/*` expands to every Gold dataset.

    `clause` and `control` are the regulation text and the plain sentence of a requirement row.
    A contract rule has no clause, and its sentence comes from CONTROL. A threshold is written
    once, in `params`, and both the query and the sentence read it from there.
    `severity` is `block` or `flag`; a flag check reports its offending records instead of a count.
    """
    if severity not in ("block", "flag"):
        raise ValueError(f"severity is 'block' or 'flag', not '{severity}', see doc/spec.md 5.3")
    names = [d for d in db.DATASETS if fnmatch(d, dataset)] or [dataset]
    checks = []
    for name in names:
        values, expected = template_values(check_kind, name, params, severity)
        template = (db.SQL / "checks" / f"{template_name(check_kind, severity)}.sql").read_text(
            encoding="utf-8")
        sql = validate(db.render(template, **values))
        detail = [str(v) for v in params.values()]
        check_id = "/".join([requirement_id, check_kind, name, *detail])
        checks.append(
            Check(check_id, requirement_id, framework, name, check_kind, severity, clause or None,
                  db.render(control, **params) if control else CONTROL[check_kind](params),
                  sql, str(expected), COMPARE[check_kind])
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
            json.loads(row["params"]), row["clause"], row["control"], row["severity"],
        )
    ]


def from_contracts(folder=CONTRACTS) -> list[Check]:
    """required and unique properties, and every ecog-lakehouse quality rule, become checks."""
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
            if rule.get("engine") == "ecog-lakehouse":
                rules.append((rule["implementation"]["check_kind"], rule["implementation"]["params"]))
        for kind, params in rules:
            checks += generate("contract", doc["id"], kind, doc["name"], params)
    return checks


def passes(compare: str, observed: str, expected: str) -> bool:
    """Numbers where both sides are numbers; a flag check reports records, so text otherwise."""
    try:
        o, e = float(observed), float(expected)
    except ValueError:
        return observed == expected
    return {"eq": o == e, "ge": o >= e, "le": o <= e}[compare]


def run(con, checks: list[Check]) -> list[dict]:
    """Run every check, append one evidence file for this run, return the evidence rows."""
    run_id = ulid()
    ran_at = datetime.now(UTC).replace(tzinfo=None)
    versions = {}
    rows = []
    for c in checks:
        version = versions.setdefault(c.dataset, db.dataset_version(c.dataset))
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
                "severity": c.severity,
                "clause": c.clause,
                "control": c.control,
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
            print(f"checks: {r['result']} {r['severity']} {r['check_id']} "
                  f"observed {r['observed']} expected {r['expected']}")
    counts = {k: sum(r["result"] == k for r in rows) for k in ("pass", "fail", "error")}
    blocking = sum(r["result"] != "pass" and r["severity"] == "block" for r in rows)
    print(f"checks: run {rows[0]['run_id']}, {counts}, {blocking} blocking")
    return 0 if blocking == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
