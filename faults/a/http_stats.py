"""GET requests and bytes received of one query, from DuckDB's EXPLAIN ANALYZE HTTP statistics.
Used by faults/a/sweep.sh for both engines.

    python faults/a/http_stats.py "<sql>"   runs EXPLAIN ANALYZE <sql> in the duckdb Python package
    python faults/a/http_stats.py -         parses an EXPLAIN ANALYZE text on stdin, the CLI's

Prints "GET requests | received", two cells of a docs/bench.md row.
"""

import re
import sys

import duckdb


def parse(text: str) -> tuple[int, str]:
    """The #GET count and the "in:" size of an EXPLAIN ANALYZE text. The CLI and the Python
    package draw different boxes around them; the two lines read the same in both."""
    gets = re.search(r"#GET: (\d+)", text)
    received = re.search(r"\bin: ([\d.]+ \w+)", text)
    if not gets or not received:
        raise ValueError("no HTTP statistics in the EXPLAIN ANALYZE text: does the query read a URL?")
    return int(gets.group(1)), received.group(1)


if __name__ == "__main__":
    if sys.argv[1] == "-":
        text = sys.stdin.read()
    else:
        text = duckdb.connect().execute("EXPLAIN ANALYZE " + sys.argv[1]).fetchall()[0][1]
    print("{} | {}".format(*parse(text)))
