"""SQLite database helpers for the MSFI app."""

import sqlite3
from flask import current_app, g


def get_db():
    """Open a per-request DB connection and attach row factory."""
    if "db" not in g:
        app_config = g.get("app_config", current_app.config)
        database_path = app_config["DATABASE"]
        connection = sqlite3.connect(database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        g.db = connection
    return g.db


def close_db(_error=None):
    """Close DB connection at request teardown."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _table_exists(db, table_name: str) -> bool:
    row = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(db, table_name: str) -> set[str]:
    rows = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _create_portfolios_table(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            buffer_1_percent REAL NOT NULL,
            buffer_2_percent REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_snapshots_table(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            snapshot_date TEXT NOT NULL,
            total_value REAL NOT NULL,
            weighted_return REAL NOT NULL,
            annual_earnings REAL NOT NULL,
            msfi REAL NOT NULL,
            buffer_1_percent REAL NOT NULL,
            buffer_2_percent REAL NOT NULL,
            buffer_1_value REAL NOT NULL,
            buffer_2_value REAL NOT NULL,
            actual_income REAL NOT NULL,
            risk_status TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
        )
        """
    )


def _ensure_default_portfolio(db) -> int:
    row = db.execute(
        """
        SELECT id
        FROM portfolios
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()
    if row is not None:
        return int(row["id"])

    cursor = db.execute(
        """
        INSERT INTO portfolios (name, buffer_1_percent, buffer_2_percent)
        VALUES (?, ?, ?)
        """,
        ("Default Portfolio", 0.10, 0.20),
    )
    return int(cursor.lastrowid)


def _migrate_legacy_snapshots_if_needed(db):
    if not _table_exists(db, "snapshots"):
        _create_snapshots_table(db)
        return

    columns = _table_columns(db, "snapshots")
    is_new_schema = "portfolio_id" in columns and "actual_income" in columns and "risk_status" in columns
    if is_new_schema:
        return

    if "actual_fortnightly_income" not in columns:
        # Unknown/custom schema; keep data untouched.
        return

    default_portfolio_id = _ensure_default_portfolio(db)
    db.execute("ALTER TABLE snapshots RENAME TO snapshots_legacy")
    _create_snapshots_table(db)

    # Preserve historical values from the old single-portfolio table.
    db.execute(
        """
        INSERT INTO snapshots (
            portfolio_id,
            snapshot_date,
            total_value,
            weighted_return,
            annual_earnings,
            msfi,
            buffer_1_percent,
            buffer_2_percent,
            buffer_1_value,
            buffer_2_value,
            actual_income,
            risk_status,
            notes,
            created_at
        )
        SELECT
            ?,
            snapshot_date,
            total_value,
            weighted_return,
            annual_earnings,
            msfi,
            0.10,
            0.20,
            msfi_buffer_10,
            msfi_buffer_20,
            actual_fortnightly_income,
            risk_flag,
            notes,
            created_at
        FROM snapshots_legacy
        ORDER BY id ASC
        """,
        (default_portfolio_id,),
    )
    db.execute("DROP TABLE snapshots_legacy")


def init_db():
    """Create or migrate database schema for multi-portfolio support."""
    db = get_db()
    db.execute("BEGIN")
    try:
        _create_portfolios_table(db)
        _migrate_legacy_snapshots_if_needed(db)
        _create_snapshots_table(db)
        _ensure_default_portfolio(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
