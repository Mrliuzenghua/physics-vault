from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .paths import default_db_path


def apply_connection_pragmas(conn: sqlite3.Connection, *, writable: bool = True) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if writable:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")


def connect_db(
    db_path: str | Path | None = None,
    *,
    writable: bool = True,
) -> sqlite3.Connection:
    resolved = Path(db_path) if db_path else default_db_path()
    conn = sqlite3.connect(str(resolved))
    apply_connection_pragmas(conn, writable=writable)
    return conn


@contextmanager
def db_transaction(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect_db(db_path, writable=True)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
