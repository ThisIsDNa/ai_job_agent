"""SQLite connection and initialization helpers for local job storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def create_connection(db_path: str) -> sqlite3.Connection:
    """Creates a sqlite connection, ensuring parent directories exist."""
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db(db_path: str) -> None:
    """Initializes required tables if they do not exist."""
    from app.storage.models import JOBS_OPTIONAL_COLUMNS, JOBS_TABLE_SQL

    with create_connection(db_path) as conn:
        conn.execute(JOBS_TABLE_SQL)
        cols = conn.execute("PRAGMA table_info(jobs)").fetchall()
        existing = {str(r["name"]) for r in cols}
        for col, col_type in JOBS_OPTIONAL_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type}")
        conn.commit()

