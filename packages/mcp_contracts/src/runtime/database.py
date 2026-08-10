"""Database connection factory for MCP infrastructure.

The factory has no knowledge of tables or tool workflows.  Callers supply the
configured database paths and, for the review database, an optional schema
initializer owned by the review domain.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DatabaseRuntime:
    """Create consistently configured connections for the two MCP databases."""

    formal_db_path: Callable[[], Path]
    review_db_path: Callable[[], Path]
    ensure_review_schema: Callable[[sqlite3.Connection], None] | None = None
    timeout_seconds: int = 30

    def formal_path(self) -> Path:
        return self.formal_db_path()

    def review_path(self) -> Path:
        path = self.review_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def connect_formal_read(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            f"file:{self.formal_path()}?mode=ro",
            uri=True,
            timeout=self.timeout_seconds,
        )
        self._configure(conn, query_only=True)
        return conn

    def connect_formal_write(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.formal_path(), timeout=self.timeout_seconds)
        self._configure(conn)
        return conn

    def connect_review(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.review_path(), timeout=self.timeout_seconds)
        self._configure(conn)
        conn.execute("PRAGMA journal_mode = WAL")
        if self.ensure_review_schema is not None:
            self.ensure_review_schema(conn)
        return conn

    @staticmethod
    def _configure(conn: sqlite3.Connection, *, query_only: bool = False) -> None:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        if query_only:
            conn.execute("PRAGMA query_only = ON")
