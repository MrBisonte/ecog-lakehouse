"""The wall clock that stamps a row: ingested_at, ran_at, produced_at and the rows of the keyring.

An entry point hands `utc_now` to the unit that stamps a row. A test hands it another clock.
The one other reader of the clock is pipeline/lid.py, for the time bits of a ULID.
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """UTC with no zone attached, the form a TIMESTAMP column of the lakehouse stores."""
    return datetime.now(UTC).replace(tzinfo=None)
