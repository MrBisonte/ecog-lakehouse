"""faults/a/encodings.sh, issue 29, without the CLI, Silver or the network: every statement of
faults/a/encodings.py on DuckDB 1.5.5 over a small Silver-shaped partition, and the queries the
script shares with faults/a/bench.sh."""

import importlib.util
import re
import subprocess
import sys

import duckdb
import pytest

from pipeline import db

A = db.REPO / "faults" / "a"
spec = importlib.util.spec_from_file_location("encodings", A / "encodings.py")
encodings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(encodings)
SQL = encodings.SQL


def one(con, name, *args):
    return [r[0] for r in con.execute(SQL[name].format(*args)).fetchall()]


@pytest.fixture(scope="module")
def variants(tmp_path_factory):
    """Two records of 250,000 samples each in shuffled order, one partition of Silver, written
    as the four variants. More distinct ts_ms per row group than DuckDB keeps a dictionary for."""
    d = tmp_path_factory.mktemp("encodings")
    con = duckdb.connect()
    con.execute(f"""COPY (
        SELECT 'faces_basic' AS experiment, 'abc' AS subject_pid, 1::SMALLINT AS run,
               (i // 250000)::SMALLINT AS channel_idx, (i % 250000)::INTEGER AS ts_ms,
               (i % 1000 / 8)::FLOAT AS value_uv,
               ('00000000-0000-0000-0000-00000000000' || (i // 250000))::UUID AS lid,
               (i % 250000)::INTEGER AS sample_idx
        FROM range(500000) t(i) ORDER BY hash(i)
    ) TO '{d}/silver.parquet' (FORMAT parquet)""")
    for v in ["v1_snappy", "v2_snappy", "v1_zstd", "v2_zstd"]:
        version, codec = v.split("_")
        con.execute(SQL["write"].format(d / "silver.parquet", d / f"{v}.parquet", version, codec))
    return con, d


def test_files_counts_files_row_groups_and_rows(variants):
    con, d = variants
    assert one(con, "files", d / "v1_snappy.parquet") == ["1 file, 3 row groups, 500,000 rows"]
    assert one(con, "files", f"{d}/v*.parquet") == ["4 files, 12 row groups, 2,000,000 rows"]


def test_write_keeps_the_sort_and_row_groups_of_fix_sql_without_partition_columns(variants):
    con, d = variants
    f = d / "v2_zstd.parquet"
    assert con.execute(f"""SELECT bool_and(ok) FROM (
        SELECT (lid, sample_idx) >= lag((lid, sample_idx)) OVER () OR lag(lid) OVER () IS NULL AS ok
        FROM read_parquet('{f}'))""").fetchone() == (True,)
    assert con.execute(f"SELECT max(row_group_num_rows) FROM parquet_metadata('{f}')").fetchone() \
        == (198656,)
    columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{f}'").fetchall()]
    assert "experiment" not in columns and "subject_pid" not in columns


def test_version_2_delta_encodes_what_version_1_stores_plain(variants):
    con, d = variants
    cells = {v: one(con, "cells", d / f"{v}.parquet")[0].split(" | ")
             for v in ["v1_snappy", "v2_snappy", "v1_zstd", "v2_zstd"]}
    assert cells["v1_snappy"][0] == "3"
    assert cells["v1_snappy"][4:] == ["PLAIN", "PLAIN", "PLAIN_DICTIONARY"]
    assert cells["v2_zstd"][4:] == ["DELTA_BINARY_PACKED", "DELTA_BINARY_PACKED", "RLE_DICTIONARY"]
    ts_bytes = {v: int(c[1].replace(",", "")) for v, c in cells.items()}
    assert ts_bytes["v2_snappy"] < ts_bytes["v1_zstd"] < ts_bytes["v1_snappy"]
    codecs = con.execute(f"SELECT DISTINCT compression FROM parquet_metadata('{d}/v1_zstd.parquet')")
    assert codecs.fetchall() == [("ZSTD",)]


def test_columns_counts_row_groups_with_a_dictionary_largest_first(variants):
    con, d = variants
    rows = one(con, "columns", d / "v1_snappy.parquet")
    assert len(rows) == 6
    assert rows[0].startswith(("| sample_idx | PLAIN | 0 of 3 |", "| ts_ms | PLAIN | 0 of 3 |"))
    assert any(r.startswith("| value_uv | PLAIN_DICTIONARY | 3 of 3 |") for r in rows)
    shares = [float(r.split(" | ")[-1].rstrip(" |")) for r in rows]
    assert shares == sorted(shares, reverse=True) and round(sum(shares)) == 100


def test_read_is_the_same_for_every_variant_and_exact(variants):
    con, d = variants
    reads = {one(con, "read", d / f"{v}.parquet")[0]
             for v in ["v1_snappy", "v2_snappy", "v1_zstd", "v2_zstd"]}
    assert reads == {"500,000 rows, sum(value_uv) 31218750.000000"}


def test_writer_names_the_engine(variants):
    con, d = variants
    writer = one(con, "writer", f"{d}/v*.parquet")[0]
    assert writer.startswith(f"DuckDB version v{duckdb.__version__} ")


def test_the_entry_point_prints_the_filled_statement():
    out = subprocess.run([sys.executable, str(A / "encodings.py"), "read", "x.parquet"],
                         capture_output=True, text=True, check=True).stdout
    assert out.strip() == SQL["read"].format("x.parquet").strip()


def test_the_queries_and_http_stats_are_those_of_bench_sh():
    def shared(path):
        text = path.read_text()
        lines = re.findall(r"(?m)^(?:SETUP|AGGREGATE|ONE_RECORD)=.*$", text)
        return lines, re.search(r"(?ms)^http\(\) \{\n.*?^\}", text).group(0)
    assert shared(A / "encodings.sh") == shared(A / "bench.sh")
