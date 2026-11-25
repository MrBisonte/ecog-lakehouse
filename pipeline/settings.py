"""The one home of the tuning values of the pipeline.

A value here changes how fast a result is produced, never what the result is. A unit reads its
value from this module and writes no literal of its own.
"""

# Seconds one download waits on the Stanford repository before its row fails, pipeline/fetch.py.
FETCH_TIMEOUT_S = 120
