"""The formatting of docs/bench.md, without a build."""

import datetime

from pipeline import bench_doc


def test_numbers_read_with_separators_mib_and_two_decimals():
    assert bench_doc.fmt_int(15336887) == "15,336,887"
    assert bench_doc.fmt_mib(1360689759) == "1,297.65 MiB"
    assert bench_doc.fmt_seconds(0.0934) == "0.09"


def test_cell_picks_the_format_from_the_value_and_the_column():
    assert bench_doc.cell("samples", 189253080) == "189,253,080"
    assert bench_doc.cell("bronze_bytes", 1360689759) == "1,297.65 MiB"
    assert bench_doc.cell("wall_clock", datetime.timedelta(minutes=6, seconds=7.136034)) == "367.14"
    assert bench_doc.cell("sorted", True) == "true"
    assert bench_doc.cell("silver_bytes", None) == "NULL"
    assert bench_doc.cell("experiment", "faces_basic") == "faces_basic"


def test_table_formats_every_cell():
    text = bench_doc.table(["experiment", "samples"], [("fingerflex", 258340520)])
    assert text.splitlines() == ["| experiment | samples |", "|---|---|", "| fingerflex | 258,340,520 |"]


def test_mem_total_is_read_in_bytes_and_none_when_missing():
    assert bench_doc.mem_total_bytes("MemFree: 1 kB\nMemTotal:       16303540 kB\n") == 16303540 * 1024
    assert bench_doc.mem_total_bytes("MemFree: 1 kB\n") is None


def test_network_location_is_base_url_or_loopback():
    assert bench_doc.network_location({"BASE_URL": "https://example.org/data"}) == "https://example.org/data"
    assert bench_doc.network_location({}) == "loopback"
    assert bench_doc.network_location({"BASE_URL": ""}) == "loopback"


def test_sections_the_fault_scripts_wrote_survive_a_rewrite():
    faults = "## Fault A: one\n\na\n\n## Fault A sweep\n\nb\n"
    assert bench_doc.other_sections("# Benchmarks\n\n## Setup\n\nx\n\n## Build\n\ny\n\n" + faults) == faults
    assert bench_doc.other_sections("# Benchmarks\n\n## Setup\n\nx\n") == ""


def test_cli_version_says_not_installed_when_absent(tmp_path):
    assert bench_doc.cli_version(tmp_path / "duckdb") == "not installed"


def test_cli_sha256_names_the_exact_binary(tmp_path):
    cli = tmp_path / "duckdb"
    assert bench_doc.cli_sha256(cli) == "not installed"
    cli.write_bytes(b"abc")
    assert bench_doc.cli_sha256(cli) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
