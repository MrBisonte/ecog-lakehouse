"""CITATION.cff stays complete, in step with pyproject.toml and with docs/data/LICENSE.md."""

import re
import tomllib

import yaml

from pipeline import db

CFF = yaml.safe_load((db.REPO / "CITATION.cff").read_text(encoding="utf-8"))
PYPROJECT = tomllib.loads((db.REPO / "pyproject.toml").read_text(encoding="utf-8"))
REFERENCE_DOIS = [r["doi"] for r in CFF.get("references", []) if "doi" in r]


def test_required_fields_are_present():
    for field in ("cff-version", "title", "authors", "version", "license", "repository-code"):
        assert CFF.get(field), field


def test_version_matches_pyproject():
    assert str(CFF["version"]) == PYPROJECT["project"]["version"]


def test_every_doi_is_well_formed():
    dois = REFERENCE_DOIS + ([CFF["doi"]] if "doi" in CFF else [])
    assert dois
    for doi in dois:
        assert re.fullmatch(r"10\.\d{4,}/\S+", doi), doi


def test_every_reference_doi_is_cited_in_the_data_licence():
    licence = (db.REPO / "docs" / "data" / "LICENSE.md").read_text(encoding="utf-8")
    missing = [doi for doi in REFERENCE_DOIS if doi not in licence]
    assert not missing, f"cite these in docs/data/LICENSE.md: {missing}"
