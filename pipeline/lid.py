"""ULID text for ingest_id and run_id. Lineage identifiers themselves are built in SQL."""

import secrets
import time

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def base32(x: int) -> str:
    """128 bits as 26 Crockford base32 characters, most significant first."""
    return "".join(ALPHABET[(x >> (125 - 5 * i)) & 31] for i in range(26))


def ulid() -> str:
    """48 bits of millisecond time followed by 80 random bits."""
    return base32((int(time.time() * 1000) << 80) | secrets.randbits(80))
