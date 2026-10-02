"""The documents quote the source; these tests keep the quotes true."""

import re

from pipeline import db


def lf(path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def test_five_records_shows_the_sql_files_as_they_are():
    """A folded block titled with one SQL file is that file, so the walkthrough cannot go stale."""
    doc = lf(db.REPO / "docs" / "five-records.md")
    blocks = re.findall(r"<summary>(sql/\S+\.sql)</summary>\n\n```sql\n(.*?)\n```", doc, re.DOTALL)
    assert len(blocks) == 8
    for name, block in blocks:
        assert block == lf(db.REPO / name).rstrip("\n"), name


def test_adr_index_status_equals_each_record():
    """The index row of every ADR names the status its own file states."""
    index_md = lf(db.REPO / "adr" / "README.md")
    index = dict(re.findall(r"^\| (\d{4}) \|.*\| (\w+) \|$", index_md, re.MULTILINE))
    records = sorted((db.REPO / "adr").glob("ADR-*.md"))
    assert records
    for path in records:
        status = re.search(r"^\| Status \| (\w+) \|$", lf(path), re.MULTILINE).group(1)
        assert index.get(path.stem[4:]) == status, path.name
