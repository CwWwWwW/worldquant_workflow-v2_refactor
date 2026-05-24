from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def immediate_transaction(conn: sqlite3.Connection, *, retries: int = 5) -> Iterator[None]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except Exception:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
            return
        except sqlite3.OperationalError as exc:
            last_error = exc
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                raise
            time.sleep(0.2 * (attempt + 1))
    if last_error is not None:
        raise last_error
