import pytest
import yaml

from pipeline import db

CONTRACTS = sorted((db.REPO / "contracts").glob("*.yaml"))


def load(path):
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["apiVersion"].startswith("v3") and doc["kind"] == "DataContract"
    [obj] = doc["schema"]
    assert obj["physicalName"] == doc["name"] and obj["physicalType"] == "parquet"
    return doc["name"], obj


def test_a_row_that_differs_from_its_contract_is_refused(tmp_path, monkeypatch):
    """A column on one side only stops the write. It is never filled with NULL."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    con = db.connect()
    row = dict.fromkeys(db.column_names("gold/dataset_manifest"))
    db.stage_rows(con, "staged", "gold/dataset_manifest", [row])
    assert con.execute("SELECT count(*) FROM staged").fetchone() == (1,)
    short = {k: v for k, v in row.items() if k != "git_commit"}
    with pytest.raises(ValueError, match="git_commit"):
        db.stage_rows(con, "staged", "gold/dataset_manifest", [short])
    with pytest.raises(ValueError, match="not_in_the_contract"):
        db.stage_rows(con, "staged", "gold/dataset_manifest", [{**row, "not_in_the_contract": 1}])


def test_one_contract_per_silver_and_gold_dataset():
    assert [load(p)[0] for p in CONTRACTS] == sorted(
        d for d in db.DATASETS if not d.startswith("bronze/")
    )


@pytest.mark.parametrize("path", CONTRACTS, ids=[p.stem for p in CONTRACTS])
def test_contract_columns_and_types_match_the_parquet_written(path, built):
    dataset, obj = load(path)
    assert any((built / dataset).rglob("*.parquet")), f"{dataset} was not written"
    declared = [(p["name"], p["physicalType"]) for p in obj["properties"]]
    written = [
        (r[0], r[1]) for r in db.connect().execute(f"DESCRIBE {db.view_name(dataset)}").fetchall()
    ]
    assert declared == written
