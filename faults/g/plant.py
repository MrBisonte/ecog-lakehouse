"""Fault G plant, spec 6: the SQL a naive metadata driven generator emits for "channel in this
list": one OR per channel, each nested one level deeper, 512 levels; and the same with one
parenthesis missing. The fix is what pipeline/checks.py emits, `channel_idx IN (...)`, and
what it refuses, anything that does not parse or nests deeper than MAX_NESTING.

    python faults/g/plant.py <out_dir>

Writes nested.sql, malformed.sql and fixed.sql under out_dir and prints the three sizes.
"""

import sys
from pathlib import Path

CHANNELS = 512
TABLE = "silver_record"


def nested(depth: int) -> str:
    predicate = "channel_idx = 0"
    for c in range(1, depth):
        predicate = f"({predicate} OR channel_idx = {c})"
    return f"SELECT count(*) FROM {TABLE} WHERE {predicate}"


def fixed(depth: int) -> str:
    return f"SELECT count(*) FROM {TABLE} WHERE channel_idx IN ({', '.join(map(str, range(depth)))})"


def main(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    variants = {
        "nested.sql": nested(CHANNELS),
        "malformed.sql": nested(CHANNELS)[:-1],  # the closing parenthesis a generator forgets
        "fixed.sql": fixed(CHANNELS),
    }
    for name, sql in variants.items():
        (out / name).write_text(sql + "\n", encoding="utf-8")
        print(f"{name}: {len(sql)} characters, nesting {sql.count('(')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
