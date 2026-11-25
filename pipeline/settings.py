"""The one home of the tuning values of the pipeline.

A value here changes how fast a result is produced, never what the result is. A unit reads its
value from this module, or is handed it as a placeholder of its SQL, and writes no literal of
its own.
"""

# Seconds one download waits on the Stanford repository before its row fails, pipeline/fetch.py.
FETCH_TIMEOUT_S = 120

# The Parquet format version of every Silver dataset, ADR-0007.
PARQUET_VERSION = "v2"

# Rows a row group of silver/recording is asked to hold, doc/spec.md 3.2. The limit is 200,000,
# a row of governance/requirements.csv. DuckDB rounds a size up to a multiple of 2,048, and this
# is the largest multiple under the limit.
ROW_GROUP_SIZE = 198656
