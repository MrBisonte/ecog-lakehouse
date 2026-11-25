"""The one home of the tuning values of the pipeline.

A value here changes how fast a result is produced and how its files are laid out, never the
rows a dataset holds. The bytes of a file do change with it, and with them the dataset_version
of doc/spec.md 5.3. A unit reads its value from this module, or is handed it as a placeholder
of its SQL.
"""

# Seconds one download waits on the Stanford repository before its row fails, pipeline/fetch.py.
FETCH_TIMEOUT_S = 120

# Bytes one download copies to disk at a time, pipeline/fetch.py.
FETCH_CHUNK_BYTES = 1 << 20

# DuckDB's preserve_insertion_order, as the text SET takes, pipeline/db.py. Every ORDER BY in
# sql/ is explicit. Keeping arrival order across parallel joins held 12 GB of Silver in memory
# on gold/channel_quality and failed on 871 million rows.
PRESERVE_INSERTION_ORDER = "false"

# The Parquet format version of every Silver dataset, ADR-0007.
PARQUET_VERSION = "v2"

# Rows a row group of silver/recording is asked to hold, doc/spec.md 3.2. The limit is 200,000,
# a row of governance/requirements.csv. DuckDB rounds a size up to a multiple of 2,048, and this
# is the largest multiple under the limit.
ROW_GROUP_SIZE = 198656
