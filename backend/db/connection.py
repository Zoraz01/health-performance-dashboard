"""
Connection helpers and path constants for both databases.

Both files live on NVME at /Volumes/NVME/health-dashboard/data/.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

import duckdb

from config import settings

_DB_DIR = settings.db_dir
SQLITE_PATH = str(_DB_DIR / "health_app.sqlite")
DUCKDB_PATH = str(_DB_DIR / "health_raw.duckdb")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_sqlite() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(SQLITE_PATH, isolation_level=None)  # autocommit
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_duckdb() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    # Fresh connection per call — DuckDB doesn't allow concurrent write connections.
    con = duckdb.connect(DUCKDB_PATH)
    try:
        yield con
    finally:
        con.close()
