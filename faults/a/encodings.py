"""The SQL of faults/a/encodings.sh, issue 29, kept apart so the tests run every statement on
DuckDB 1.5.5 without the CLI, Silver or the network. Each statement is a template filled by
position; the result is one VARCHAR column, a markdown cell or row per line.

    python faults/a/encodings.py <statement> <argument...>   prints the statement, filled in
"""

import sys

SQL = {
    # {0}: a glob of Parquet files. "12 files, 345 row groups, 6,789 rows".
    "files": """
        SELECT printf('%,d file%s, %,d row groups, %,d rows', count(*),
                      CASE count(*) WHEN 1 THEN '' ELSE 's' END,
                      sum(num_row_groups)::BIGINT, sum(num_rows)::BIGINT)
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
    # {0}: the Silver files of one partition, {1}: the target file, {2}: v1 or v2, {3}: snappy
    # or zstd. The sort order and row group size of fix.sql, and the columns of its output:
    # PARTITION_BY leaves the partition columns out of the file. One file, as the pipeline writes.
    "write": """
        COPY (
            SELECT * EXCLUDE (experiment, subject_pid)
            FROM read_parquet('{0}', hive_partitioning = false)
            ORDER BY lid, sample_idx
        ) TO '{1}'
        (FORMAT parquet, PARQUET_VERSION {2}, COMPRESSION {3}, ROW_GROUP_SIZE 198656)""",
    # {0}: one Parquet file. "37 | 1,234 | 1,234 | 5,678 | PLAIN | PLAIN | PLAIN_DICTIONARY":
    # row groups, then compressed bytes and encodings of ts_ms, sample_idx and value_uv.
    "cells": """
        WITH per_column AS (
            SELECT list_position(['ts_ms', 'sample_idx', 'value_uv'], path_in_schema) AS i,
                   count(*) AS row_groups, sum(total_compressed_size)::BIGINT AS packed,
                   string_agg(DISTINCT encodings, ', ' ORDER BY encodings) AS encodings
            FROM parquet_metadata('{0}')
            WHERE path_in_schema IN ('ts_ms', 'sample_idx', 'value_uv')
            GROUP BY path_in_schema
        )
        SELECT printf('%,d | ', max(row_groups))
            || string_agg(printf('%,d', packed), ' | ' ORDER BY i) || ' | '
            || string_agg(encodings, ' | ' ORDER BY i)
        FROM per_column""",
    # {0}: one Parquet file. Row count and an exact sum: a DECIMAL sum does not depend on the
    # order threads add the values in, a FLOAT sum does. Through DOUBLE because DuckDB 1.5.5
    # casts FLOAT to DECIMAL in float precision and the CLI does not: 123.456787109375 gives
    # 123.456784 against 123.456787.
    "read": """
        SELECT printf('%,d rows, sum(value_uv) ', count(*))
            || sum(value_uv::DOUBLE::DECIMAL(38, 6))
        FROM read_parquet('{0}')""",
    # {0}: a glob of Parquet files. The writers named in their footers.
    "writer": """
        SELECT string_agg(DISTINCT created_by, ', ') FROM parquet_file_metadata('{0}')""",
}


if __name__ == "__main__":
    print(SQL[sys.argv[1]].format(*sys.argv[2:]))
