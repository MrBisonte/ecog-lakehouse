"""The wall clock, read here and nowhere else in the pipeline.

An entry point hands `utc_now` to the unit that stamps a row. A test hands it another clock.
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """UTC with no zone attached, the form a TIMESTAMP column of the lakehouse stores."""
    return datetime.now(UTC).replace(tzinfo=None)
