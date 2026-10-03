"""The SQL of faults/a/encodings.sh, issue 29, kept apart so the tests run every statement on
DuckDB 1.5.5 without the CLI, Silver or the network. Each statement is a template filled by
position; the result is one VARCHAR column, a markdown cell or row per line.

    python faults/a/encodings.py <statement> <argument...>   prints the statement, filled in
"""

import sys

SQL = {
    # {0}: a glob of Parquet files. "12 files, 345 row groups, 6,789 rows".
    "files": """
        SELECT printf('%,d files, %,d row groups, %,d rows',
                      count(*), sum(num_row_groups)::BIGINT, sum(num_rows)::BIGINT)
        FROM parquet_file_metadata('{0}')""",
    # {0}: a glob of Parquet files. One markdown row per column, the largest first: encodings in
    # use, row groups whose column chunk has a dictionary page, compressed and uncompressed
    # bytes, compressed bytes per value, share of all compressed bytes in percent.
    "columns": """
        WITH chunk AS (
            SELECT path_in_schema AS col, encodings, num_values,
                   dictionary_page_offset IS NOT NULL AS dictionary,
                   total_compressed_size AS packed, total_uncompressed_size AS raw
            FROM parquet_metadata('{0}')
        ), per_column AS (
            SELECT col, string_agg(DISTINCT encodings, ', ' ORDER BY encodings) AS encodings,
                   count(*) FILTER (dictionary) AS dictionary_groups, count(*) AS row_groups,
                   sum(num_values)::BIGINT AS n, sum(packed)::BIGINT AS packed,
                   sum(raw)::BIGINT AS raw
            FROM chunk GROUP BY col
        )
        SELECT printf('| %s | %s | %,d of %,d | %,d | %,d | %.2f | %.1f |', col, encodings,
                      dictionary_groups, row_groups, packed, raw, packed / n,
                      100 * packed / sum(packed) OVER ())
        FROM per_column ORDER BY packed DESC, col""",
}


if __name__ == "__main__":
    print(SQL[sys.argv[1]].format(*sys.argv[2:]))
