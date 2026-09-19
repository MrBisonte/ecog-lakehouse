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


def test_one_contract_per_silver_and_gold_dataset():
    assert [load(p)[0] for p in CONTRACTS] == sorted(
        d for d in db.DATASETS if not d.startswith("bronze/")
    )


@pytest.mark.parametrize("path", CONTRACTS, ids=[p.stem for p in CONTRACTS])
def test_contract_columns_and_types_match_the_parquet_written(path, built):
    dataset, obj = load(path)
    if not any((built / dataset).rglob("*.parquet")):
        pytest.skip(f"{dataset} is not written by the layers built in this session")
    declared = [(p["name"], p["physicalType"]) for p in obj["properties"]]
    written = [
        (r[0], r[1]) for r in db.connect().execute(f"DESCRIBE {db.view_name(dataset)}").fetchall()
    ]
    assert declared == written
