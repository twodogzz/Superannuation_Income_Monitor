"""Data access layer for portfolios and snapshots."""

from __future__ import annotations

from database import get_db


def get_all_portfolios():
    """Fetch all portfolios by name."""
    db = get_db()
    return db.execute(
        """
        SELECT *
        FROM portfolios
        ORDER BY name ASC
        """
    ).fetchall()


def get_portfolio_by_id(portfolio_id: int):
    """Fetch one portfolio by id."""
    db = get_db()
    return db.execute(
        """
        SELECT *
        FROM portfolios
        WHERE id = ?
        """,
        (portfolio_id,),
    ).fetchone()


def create_portfolio(name: str, buffer_1_percent: float, buffer_2_percent: float) -> int:
    """Create a new portfolio with default future buffer settings."""
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO portfolios (name, buffer_1_percent, buffer_2_percent)
        VALUES (?, ?, ?)
        """,
        (name, buffer_1_percent, buffer_2_percent),
    )
    db.commit()
    return int(cursor.lastrowid)


def update_portfolio_buffers(portfolio_id: int, buffer_1_percent: float, buffer_2_percent: float) -> None:
    """Update only future default buffers on a portfolio."""
    db = get_db()
    db.execute(
        """
        UPDATE portfolios
        SET buffer_1_percent = ?, buffer_2_percent = ?
        WHERE id = ?
        """,
        (buffer_1_percent, buffer_2_percent, portfolio_id),
    )
    db.commit()


def get_latest_snapshot_by_portfolio(portfolio_id: int):
    """Fetch latest snapshot for one portfolio."""
    db = get_db()
    return db.execute(
        """
        SELECT *
        FROM snapshots
        WHERE portfolio_id = ?
        ORDER BY snapshot_date DESC, id DESC
        LIMIT 1
        """,
        (portfolio_id,),
    ).fetchone()


def get_chart_snapshots_by_portfolio(portfolio_id: int):
    """Fetch chart series for one portfolio in chronological order."""
    db = get_db()
    return db.execute(
        """
        SELECT snapshot_date, total_value, msfi, actual_income
        FROM snapshots
        WHERE portfolio_id = ?
        ORDER BY snapshot_date ASC, id ASC
        """,
        (portfolio_id,),
    ).fetchall()


def get_snapshots_by_portfolio(portfolio_id: int):
    """Fetch all snapshots for one portfolio newest first."""
    db = get_db()
    return db.execute(
        """
        SELECT s.*, p.name AS portfolio_name
        FROM snapshots s
        INNER JOIN portfolios p ON p.id = s.portfolio_id
        WHERE s.portfolio_id = ?
        ORDER BY s.snapshot_date DESC, s.id DESC
        """,
        (portfolio_id,),
    ).fetchall()


def get_snapshot_by_id(snapshot_id: int):
    """Fetch one snapshot by id."""
    db = get_db()
    return db.execute(
        """
        SELECT s.*, p.name AS portfolio_name
        FROM snapshots s
        INNER JOIN portfolios p ON p.id = s.portfolio_id
        WHERE s.id = ?
        """,
        (snapshot_id,),
    ).fetchone()


def insert_snapshot(snapshot: dict) -> int:
    """Insert one snapshot record with snapshot-specific buffer values."""
    db = get_db()
    cursor = db.execute(
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
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot["portfolio_id"],
            snapshot["snapshot_date"],
            snapshot["total_value"],
            snapshot["weighted_return"],
            snapshot["annual_earnings"],
            snapshot["msfi"],
            snapshot["buffer_1_percent"],
            snapshot["buffer_2_percent"],
            snapshot["buffer_1_value"],
            snapshot["buffer_2_value"],
            snapshot["actual_income"],
            snapshot["risk_status"],
            snapshot.get("notes", ""),
        ),
    )
    db.commit()
    return int(cursor.lastrowid)


def update_snapshot(snapshot_id: int, snapshot: dict) -> None:
    """Update one snapshot with recalculated dependent values."""
    db = get_db()
    db.execute(
        """
        UPDATE snapshots
        SET
            snapshot_date = ?,
            total_value = ?,
            weighted_return = ?,
            annual_earnings = ?,
            msfi = ?,
            buffer_1_percent = ?,
            buffer_2_percent = ?,
            buffer_1_value = ?,
            buffer_2_value = ?,
            actual_income = ?,
            risk_status = ?,
            notes = ?
        WHERE id = ?
        """,
        (
            snapshot["snapshot_date"],
            snapshot["total_value"],
            snapshot["weighted_return"],
            snapshot["annual_earnings"],
            snapshot["msfi"],
            snapshot["buffer_1_percent"],
            snapshot["buffer_2_percent"],
            snapshot["buffer_1_value"],
            snapshot["buffer_2_value"],
            snapshot["actual_income"],
            snapshot["risk_status"],
            snapshot.get("notes", ""),
            snapshot_id,
        ),
    )
    db.commit()


def delete_snapshot(snapshot_id: int) -> None:
    """Delete one snapshot by id."""
    db = get_db()
    db.execute(
        """
        DELETE FROM snapshots
        WHERE id = ?
        """,
        (snapshot_id,),
    )
    db.commit()
