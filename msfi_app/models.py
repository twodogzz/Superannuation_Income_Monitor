"""Data access layer for portfolios, strategies, and snapshots."""

from __future__ import annotations

from database import get_db


def get_all_portfolios():
    db = get_db()
    return db.execute("SELECT * FROM portfolios ORDER BY name ASC").fetchall()


def get_portfolio_by_id(portfolio_id: int):
    db = get_db()
    return db.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,)).fetchone()


def create_portfolio(name: str, buffer_1_percent: float, buffer_2_percent: float) -> int:
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


def update_portfolio(portfolio_id: int, name: str, buffer_1_percent: float, buffer_2_percent: float) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE portfolios
        SET name = ?, buffer_1_percent = ?, buffer_2_percent = ?
        WHERE id = ?
        """,
        (name, buffer_1_percent, buffer_2_percent, portfolio_id),
    )
    db.commit()


def portfolio_snapshot_count(portfolio_id: int) -> int:
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM snapshots WHERE portfolio_id = ?",
        (portfolio_id,),
    ).fetchone()
    return int(row["cnt"])


def delete_portfolio_if_empty(portfolio_id: int) -> bool:
    if portfolio_snapshot_count(portfolio_id) > 0:
        return False
    db = get_db()
    db.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
    db.commit()
    return True


def get_strategies_by_portfolio(portfolio_id: int, include_inactive: bool = False):
    db = get_db()
    if include_inactive:
        return db.execute(
            """
            SELECT *
            FROM strategies
            WHERE portfolio_id = ?
            ORDER BY id ASC
            """,
            (portfolio_id,),
        ).fetchall()
    return db.execute(
        """
        SELECT *
        FROM strategies
        WHERE portfolio_id = ? AND active_flag = 1
        ORDER BY id ASC
        """,
        (portfolio_id,),
    ).fetchall()


def get_strategy_by_id(strategy_id: int):
    db = get_db()
    return db.execute(
        """
        SELECT s.*, p.name AS portfolio_name
        FROM strategies s
        INNER JOIN portfolios p ON p.id = s.portfolio_id
        WHERE s.id = ?
        """,
        (strategy_id,),
    ).fetchone()


def create_strategy(portfolio_id: int, name: str, default_return_5yr: float, active_flag: int) -> int:
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO strategies (portfolio_id, name, default_return_5yr, active_flag)
        VALUES (?, ?, ?, ?)
        """,
        (portfolio_id, name, default_return_5yr, active_flag),
    )
    db.commit()
    return int(cursor.lastrowid)


def update_strategy(strategy_id: int, name: str, default_return_5yr: float, active_flag: int) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE strategies
        SET name = ?, default_return_5yr = ?, active_flag = ?
        WHERE id = ?
        """,
        (name, default_return_5yr, active_flag, strategy_id),
    )
    db.commit()


def strategy_usage_count(strategy_id: int) -> int:
    db = get_db()
    row = db.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM snapshot_strategy_values
        WHERE strategy_id = ?
        """,
        (strategy_id,),
    ).fetchone()
    return int(row["cnt"])


def delete_strategy_if_unused(strategy_id: int) -> bool:
    if strategy_usage_count(strategy_id) > 0:
        return False
    db = get_db()
    db.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    db.commit()
    return True


def get_latest_snapshot_by_portfolio(portfolio_id: int):
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


def get_snapshot_strategy_rows(snapshot_id: int):
    db = get_db()
    return db.execute(
        """
        SELECT ssv.*, st.name AS strategy_name, st.active_flag
        FROM snapshot_strategy_values ssv
        INNER JOIN strategies st ON st.id = ssv.strategy_id
        WHERE ssv.snapshot_id = ?
        ORDER BY st.id ASC
        """,
        (snapshot_id,),
    ).fetchall()


def insert_snapshot_with_strategies(snapshot_payload: dict, strategy_rows: list[dict]) -> int:
    db = get_db()
    db.execute("BEGIN")
    try:
        cursor = db.execute(
            """
            INSERT INTO snapshots (
                portfolio_id, snapshot_date, total_value, weighted_return, annual_earnings, msfi,
                buffer_1_percent, buffer_2_percent, buffer_1_value, buffer_2_value,
                actual_income, risk_status, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_payload["portfolio_id"],
                snapshot_payload["snapshot_date"],
                snapshot_payload["total_value"],
                snapshot_payload["weighted_return"],
                snapshot_payload["annual_earnings"],
                snapshot_payload["msfi"],
                snapshot_payload["buffer_1_percent"],
                snapshot_payload["buffer_2_percent"],
                snapshot_payload["buffer_1_value"],
                snapshot_payload["buffer_2_value"],
                snapshot_payload["actual_income"],
                snapshot_payload["risk_status"],
                snapshot_payload.get("notes", ""),
            ),
        )
        snapshot_id = int(cursor.lastrowid)

        for row in strategy_rows:
            db.execute(
                """
                INSERT INTO snapshot_strategy_values (snapshot_id, strategy_id, strategy_value, return_used)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, row["strategy_id"], row["strategy_value"], row["return_used"]),
            )

        db.commit()
        return snapshot_id
    except Exception:
        db.rollback()
        raise


def update_snapshot_with_strategies(snapshot_id: int, snapshot_payload: dict, strategy_rows: list[dict]) -> None:
    db = get_db()
    db.execute("BEGIN")
    try:
        db.execute(
            """
            UPDATE snapshots
            SET
                snapshot_date = ?, total_value = ?, weighted_return = ?, annual_earnings = ?, msfi = ?,
                buffer_1_percent = ?, buffer_2_percent = ?, buffer_1_value = ?, buffer_2_value = ?,
                actual_income = ?, risk_status = ?, notes = ?
            WHERE id = ?
            """,
            (
                snapshot_payload["snapshot_date"],
                snapshot_payload["total_value"],
                snapshot_payload["weighted_return"],
                snapshot_payload["annual_earnings"],
                snapshot_payload["msfi"],
                snapshot_payload["buffer_1_percent"],
                snapshot_payload["buffer_2_percent"],
                snapshot_payload["buffer_1_value"],
                snapshot_payload["buffer_2_value"],
                snapshot_payload["actual_income"],
                snapshot_payload["risk_status"],
                snapshot_payload.get("notes", ""),
                snapshot_id,
            ),
        )
        db.execute("DELETE FROM snapshot_strategy_values WHERE snapshot_id = ?", (snapshot_id,))

        for row in strategy_rows:
            db.execute(
                """
                INSERT INTO snapshot_strategy_values (snapshot_id, strategy_id, strategy_value, return_used)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, row["strategy_id"], row["strategy_value"], row["return_used"]),
            )

        db.commit()
    except Exception:
        db.rollback()
        raise


def delete_snapshot(snapshot_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
    db.commit()
