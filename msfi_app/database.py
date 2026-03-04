"""SQLite database helpers and schema migrations."""

from __future__ import annotations

import sqlite3
from flask import current_app, g


DEFAULT_STRATEGIES: list[tuple[str, float]] = [
    ("Growth", 0.07),
    ("Balanced", 0.05),
    ("Conservative", 0.03),
    ("Cash", 0.02),
]


def get_db():
    """Open a per-request DB connection and attach row factory."""
    if "db" not in g:
        app_config = g.get("app_config", current_app.config)
        database_path = app_config["DATABASE"]
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error=None):
    """Close DB connection at request teardown."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _table_exists(db, table_name: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
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


def _create_strategies_table(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            default_return_5yr REAL NOT NULL,
            active_flag INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portfolio_id, name),
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE RESTRICT
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
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE RESTRICT
        )
        """
    )


def _create_snapshot_strategy_values_table(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_strategy_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            strategy_id INTEGER NOT NULL,
            strategy_value REAL NOT NULL,
            return_used REAL NOT NULL,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
            FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE RESTRICT
        )
        """
    )


def _ensure_default_portfolio(db) -> int:
    row = db.execute("SELECT id FROM portfolios ORDER BY id ASC LIMIT 1").fetchone()
    if row:
        return int(row["id"])

    cursor = db.execute(
        """
        INSERT INTO portfolios (name, buffer_1_percent, buffer_2_percent)
        VALUES (?, ?, ?)
        """,
        ("Default Portfolio", 0.10, 0.20),
    )
    return int(cursor.lastrowid)


def _migrate_single_portfolio_legacy_table(db):
    """Migrate oldest schema with strategy allocation columns into current snapshots schema."""
    if not _table_exists(db, "snapshots"):
        return

    cols = _table_columns(db, "snapshots")
    if "actual_fortnightly_income" not in cols:
        return

    default_portfolio_id = _ensure_default_portfolio(db)
    db.execute("ALTER TABLE snapshots RENAME TO snapshots_legacy_old")
    _create_snapshots_table(db)
    db.execute(
        """
        INSERT INTO snapshots (
            portfolio_id, snapshot_date, total_value, weighted_return, annual_earnings, msfi,
            buffer_1_percent, buffer_2_percent, buffer_1_value, buffer_2_value,
            actual_income, risk_status, notes, created_at
        )
        SELECT
            ?, snapshot_date, total_value, weighted_return, annual_earnings, msfi,
            0.10, 0.20, msfi_buffer_10, msfi_buffer_20,
            actual_fortnightly_income, risk_flag, notes, created_at
        FROM snapshots_legacy_old
        ORDER BY id ASC
        """,
        (default_portfolio_id,),
    )
    db.execute("DROP TABLE snapshots_legacy_old")


def _recreate_snapshots_if_wrong_fk(db):
    """
    Ensure snapshots FK has RESTRICT semantics.

    Older revisions used CASCADE. This recreates the table and preserves data.
    """
    if not _table_exists(db, "snapshots"):
        return
    create_sql_row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='snapshots'"
    ).fetchone()
    create_sql = (create_sql_row["sql"] or "").upper() if create_sql_row else ""
    if "ON DELETE CASCADE" not in create_sql:
        return

    db.execute("ALTER TABLE snapshots RENAME TO snapshots_old_fk")
    _create_snapshots_table(db)
    db.execute(
        """
        INSERT INTO snapshots (
            id, portfolio_id, snapshot_date, total_value, weighted_return, annual_earnings, msfi,
            buffer_1_percent, buffer_2_percent, buffer_1_value, buffer_2_value,
            actual_income, risk_status, notes, created_at
        )
        SELECT
            id, portfolio_id, snapshot_date, total_value, weighted_return, annual_earnings, msfi,
            buffer_1_percent, buffer_2_percent, buffer_1_value, buffer_2_value,
            actual_income, risk_status, notes, created_at
        FROM snapshots_old_fk
        ORDER BY id ASC
        """
    )
    db.execute("DROP TABLE snapshots_old_fk")


def _seed_default_strategies_for_portfolio(db, portfolio_id: int):
    existing = db.execute(
        "SELECT name FROM strategies WHERE portfolio_id = ?",
        (portfolio_id,),
    ).fetchall()
    existing_names = {row["name"] for row in existing}
    for name, default_return in DEFAULT_STRATEGIES:
        if name in existing_names:
            continue
        db.execute(
            """
            INSERT INTO strategies (portfolio_id, name, default_return_5yr, active_flag)
            VALUES (?, ?, ?, 1)
            """,
            (portfolio_id, name, default_return),
        )


def _seed_default_strategies(db):
    portfolios = db.execute("SELECT id FROM portfolios ORDER BY id ASC").fetchall()
    for row in portfolios:
        _seed_default_strategies_for_portfolio(db, int(row["id"]))


def _migrate_snapshot_strategy_values(db):
    """Backfill snapshot strategy rows for pre-strategy snapshots."""
    snapshots = db.execute(
        """
        SELECT s.id, s.portfolio_id, s.total_value, s.weighted_return
        FROM snapshots s
        LEFT JOIN snapshot_strategy_values ssv ON ssv.snapshot_id = s.id
        GROUP BY s.id
        HAVING COUNT(ssv.id) = 0
        ORDER BY s.id ASC
        """
    ).fetchall()

    for snapshot in snapshots:
        snapshot_id = int(snapshot["id"])
        portfolio_id = int(snapshot["portfolio_id"])
        total_value = float(snapshot["total_value"])
        weighted_return = float(snapshot["weighted_return"] or 0.0)

        strategies = db.execute(
            """
            SELECT id, default_return_5yr
            FROM strategies
            WHERE portfolio_id = ?
            ORDER BY id ASC
            """,
            (portfolio_id,),
        ).fetchall()
        if not strategies:
            _seed_default_strategies_for_portfolio(db, portfolio_id)
            strategies = db.execute(
                """
                SELECT id, default_return_5yr
                FROM strategies
                WHERE portfolio_id = ?
                ORDER BY id ASC
                """,
                (portfolio_id,),
            ).fetchall()

        split_value = round(total_value / len(strategies), 2) if strategies else 0.0
        for idx, strategy in enumerate(strategies):
            strategy_id = int(strategy["id"])
            strategy_value = split_value
            if idx == len(strategies) - 1:
                assigned = split_value * (len(strategies) - 1)
                strategy_value = round(total_value - assigned, 2)

            db.execute(
                """
                INSERT INTO snapshot_strategy_values (snapshot_id, strategy_id, strategy_value, return_used)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, strategy_id, strategy_value, float(strategy["default_return_5yr"])),
            )

        if weighted_return == 0:
            calc = db.execute(
                """
                SELECT SUM((strategy_value / ?) * return_used) AS wr
                FROM snapshot_strategy_values
                WHERE snapshot_id = ?
                """,
                (total_value if total_value > 0 else 1.0, snapshot_id),
            ).fetchone()
            new_weighted = round(float(calc["wr"] or 0.0), 4)
            db.execute(
                "UPDATE snapshots SET weighted_return = ? WHERE id = ?",
                (new_weighted, snapshot_id),
            )


def init_db():
    """Create or migrate schema to portfolio+strategy model."""
    db = get_db()
    db.execute("BEGIN")
    try:
        _create_portfolios_table(db)
        _ensure_default_portfolio(db)
        _migrate_single_portfolio_legacy_table(db)
        _create_snapshots_table(db)
        _recreate_snapshots_if_wrong_fk(db)
        _create_strategies_table(db)
        _create_snapshot_strategy_values_table(db)
        _seed_default_strategies(db)
        _migrate_snapshot_strategy_values(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
