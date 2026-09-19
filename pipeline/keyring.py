"""keyring.duckdb: the only place a source subject code meets its pseudonym.

`subject_pid` is the first 16 hex characters of HMAC-SHA256(secret, subject_src). The secret
is generated on first use and lives in this file only. Every re-identification appends to
`access_log` before the answer is read.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

import duckdb

from pipeline import db


def path():
    return db.data_dir() / "keyring.duckdb"


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def open_keyring():
    """The keyring connection, tables created and the secret generated on first use."""
    path().parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path()))
    con.execute("CREATE TABLE IF NOT EXISTS secret (hex VARCHAR)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS key_map "
        "(subject_src VARCHAR, subject_pid VARCHAR, created_at TIMESTAMP)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS access_log "
        "(accessed_at TIMESTAMP, actor VARCHAR, purpose VARCHAR, subject_pid VARCHAR)"
    )
    if not con.execute("SELECT count(*) FROM secret").fetchone()[0]:
        con.execute("INSERT INTO secret VALUES (?)", [secrets.token_hex(32)])
    return con


def pid(secret_hex: str, subject_src: str) -> str:
    return hmac.new(bytes.fromhex(secret_hex), subject_src.encode(), hashlib.sha256).hexdigest()[:16]


def pseudonymise(codes) -> int:
    """Add a key_map row for every source code not seen before. Returns rows added."""
    con = open_keyring()
    secret = con.execute("SELECT hex FROM secret").fetchone()[0]
    known = {r[0] for r in con.execute("SELECT subject_src FROM key_map").fetchall()}
    new = sorted(set(codes) - known)
    con.executemany("INSERT INTO key_map VALUES (?, ?, ?)", [(c, pid(secret, c), now()) for c in new])
    con.close()
    return len(new)


def reidentify(subject_pid: str, actor: str, purpose: str) -> str | None:
    """Log first, then answer. The log row exists even when the pseudonym is unknown."""
    con = open_keyring()
    con.execute("INSERT INTO access_log VALUES (?, ?, ?, ?)", [now(), actor, purpose, subject_pid])
    row = con.execute(
        "SELECT subject_src FROM key_map WHERE subject_pid = ?", [subject_pid]
    ).fetchone()
    con.close()
    return row[0] if row else None
