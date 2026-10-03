"""The pure part of faults/a/sweep.sh: GET requests and bytes received out of EXPLAIN ANALYZE text.
The samples are the heads of real outputs over loopback, the 38 row group layout of fault A."""

import importlib.util
from pathlib import Path

import pytest

HELPER = Path(__file__).parents[1] / "faults" / "a" / "http_stats.py"
spec = importlib.util.spec_from_file_location("http_stats", HELPER)
http_stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(http_stats)

# DuckDB CLI v2.0.0-alpha42839: rounded boxes, a summary with "Data Read" after the HTTP stats.
CLI = """\
┌─────────────────────────────────────┐
│┌───────────────────────────────────┐│
││         HTTPFS HTTP Stats         ││
││                                   ││
││            in: 72.7 MiB           ││
││            out: 0 bytes           ││
││              #HEAD: 2             ││
││              #GET: 38             ││
││              #PUT: 0              ││
││              #POST: 0             ││
││             #DELETE: 0            ││
││            #OPTIONS: 0            ││
│└───────────────────────────────────┘│
└─────────────────────────────────────┘
╭─ Summary ──────────╮
│ Total Time:  1.31s │
│ Data Read: 76.2 MB │
╰────────────────────╯
"""

# DuckDB 1.5.5 through Python: the query text first, square boxes, no #OPTIONS line.
PYTHON = """\
┌─────────────────────────────────────┐
│┌───────────────────────────────────┐│
││    Query Profiling Information    ││
│└───────────────────────────────────┘│
└─────────────────────────────────────┘
EXPLAIN ANALYZE SELECT channel_idx, avg(value_uv), count(*) FROM read_parquet(['http://127.0.0.1:8771/faults/a/good/experiment=faces_basic/subject_pid=72d88db77f3716bb/data_0.parquet']) GROUP BY 1
┌─────────────────────────────────────┐
│┌───────────────────────────────────┐│
││         HTTPFS HTTP Stats         ││
││                                   ││
││            in: 16.2 MiB           ││
││            out: 0 bytes           ││
││              #HEAD: 2             ││
││              #GET: 78             ││
││              #PUT: 0              ││
││              #POST: 0             ││
││             #DELETE: 0            ││
│└───────────────────────────────────┘│
└─────────────────────────────────────┘
"""


@pytest.mark.parametrize(("text", "expected"), [(CLI, (38, "72.7 MiB")), (PYTHON, (78, "16.2 MiB"))])
def test_parse_reads_gets_and_received_in_both_engines_formats(text, expected):
    assert http_stats.parse(text) == expected


def test_parse_refuses_a_plan_without_http_statistics():
    with pytest.raises(ValueError, match="no HTTP statistics"):
        http_stats.parse(CLI.replace("#GET", "#GOT"))
