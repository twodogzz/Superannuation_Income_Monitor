"""MSFI Monitoring Flask application with portfolio + strategy model."""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import Flask, abort, redirect, render_template, request, url_for

from calculations import (
    calculate_buffer_values,
    calculate_income_metrics,
    calculate_risk_status,
    calculate_weighted_return,
    normalize_return_percent_input,
)
from config import Config
from database import close_db, init_db
from models import (
    create_portfolio,
    create_strategy,
    delete_portfolio_if_empty,
    delete_snapshot,
    delete_strategy_if_unused,
    get_all_portfolios,
    get_chart_snapshots_by_portfolio,
    get_latest_snapshot_by_portfolio,
    get_portfolio_by_id,
    get_snapshot_by_id,
    get_snapshot_strategy_rows,
    get_snapshots_by_portfolio,
    get_strategies_by_portfolio,
    get_strategy_by_id,
    insert_snapshot_with_strategies,
    portfolio_snapshot_count,
    strategy_usage_count,
    update_portfolio,
    update_snapshot_with_strategies,
    update_strategy,
)


DEFAULT_BUFFER_1_PERCENT = "10"
DEFAULT_BUFFER_2_PERCENT = "20"
TOTAL_TOLERANCE = 0.01


def _safe_next_path(next_path: str | None) -> str:
    if next_path and next_path.startswith("/"):
        return next_path
    return url_for("dashboard")


def _risk_explanation(risk_status: str, buffer_1_percent: float) -> str:
    buffer_label = round(buffer_1_percent * 100, 2)
    if risk_status == "Overdrawing":
        return "Actual income is above MSFI"
    if risk_status == "Caution":
        return f"Actual income is above {buffer_label}% buffer"
    return f"Actual income is below {buffer_label}% buffer"


def _parse_percent_input(raw_value: str) -> float:
    value = float(raw_value)
    if value < 0 or value >= 100:
        raise ValueError("Buffer percentages must be between 0 and 99.99.")
    return value / 100.0


def _parse_buffer_pair(buffer_1_raw: str, buffer_2_raw: str) -> tuple[float, float]:
    return _parse_percent_input(buffer_1_raw), _parse_percent_input(buffer_2_raw)


def _active_portfolio_id() -> int | None:
    portfolios = get_all_portfolios()
    if not portfolios:
        return None
    requested_id = request.args.get("portfolio_id", type=int)
    if requested_id is not None and any(int(p["id"]) == requested_id for p in portfolios):
        return requested_id
    return int(portfolios[0]["id"])


def _portfolio_create_form_defaults() -> dict[str, str]:
    return {"name": "", "buffer_1_percent": DEFAULT_BUFFER_1_PERCENT, "buffer_2_percent": DEFAULT_BUFFER_2_PERCENT}


def _portfolio_create_form_from_request() -> dict[str, str]:
    return {
        "name": request.form.get("name", "").strip(),
        "buffer_1_percent": request.form.get("buffer_1_percent", DEFAULT_BUFFER_1_PERCENT).strip(),
        "buffer_2_percent": request.form.get("buffer_2_percent", DEFAULT_BUFFER_2_PERCENT).strip(),
    }


def _portfolio_edit_form_from_portfolio(portfolio: Any) -> dict[str, str]:
    return {
        "name": portfolio["name"],
        "buffer_1_percent": str(round(float(portfolio["buffer_1_percent"]) * 100, 4)),
        "buffer_2_percent": str(round(float(portfolio["buffer_2_percent"]) * 100, 4)),
    }


def _portfolio_edit_form_from_request() -> dict[str, str]:
    return {
        "name": request.form.get("name", "").strip(),
        "buffer_1_percent": request.form.get("buffer_1_percent", "").strip(),
        "buffer_2_percent": request.form.get("buffer_2_percent", "").strip(),
    }


def _strategy_create_form_defaults() -> dict[str, str]:
    return {"name": "", "default_return_5yr_percent": "7.00", "active_flag": "1"}


def _strategy_create_form_from_request() -> dict[str, str]:
    return {
        "name": request.form.get("name", "").strip(),
        "default_return_5yr_percent": request.form.get("default_return_5yr_percent", "").strip(),
        "active_flag": "1" if request.form.get("active_flag") else "0",
    }


def _strategy_edit_form_from_strategy(strategy: Any) -> dict[str, str]:
    return {
        "name": strategy["name"],
        "default_return_5yr_percent": str(round(float(strategy["default_return_5yr"]) * 100, 4)),
        "active_flag": "1" if int(strategy["active_flag"]) == 1 else "0",
    }


def _strategy_edit_form_from_request() -> dict[str, str]:
    return {
        "name": request.form.get("name", "").strip(),
        "default_return_5yr_percent": request.form.get("default_return_5yr_percent", "").strip(),
        "active_flag": "1" if request.form.get("active_flag") else "0",
    }


def _snapshot_form_defaults() -> dict[str, str]:
    return {"snapshot_date": "", "total_value": "", "actual_income": "", "notes": ""}


def _snapshot_form_from_snapshot(snapshot: Any) -> dict[str, str]:
    return {
        "snapshot_date": snapshot["snapshot_date"],
        "total_value": str(snapshot["total_value"]),
        "actual_income": str(snapshot["actual_income"]),
        "notes": snapshot["notes"] or "",
        "buffer_1_percent": str(round(float(snapshot["buffer_1_percent"]) * 100, 4)),
        "buffer_2_percent": str(round(float(snapshot["buffer_2_percent"]) * 100, 4)),
    }


def _parse_strategy_rows_for_new_snapshot(strategies: list[Any], form_data: Any) -> list[dict]:
    rows: list[dict] = []
    for strategy in strategies:
        strategy_id = int(strategy["id"])
        value_raw = form_data.get(f"strategy_value_{strategy_id}", "").strip()
        return_override_raw = form_data.get(f"return_percent_{strategy_id}", "").strip()
        if not value_raw:
            raise ValueError(f"Strategy value is required for {strategy['name']}.")
        strategy_value = float(value_raw)
        if strategy_value < 0:
            raise ValueError(f"Strategy value must be non-negative for {strategy['name']}.")

        if return_override_raw == "":
            return_used = float(strategy["default_return_5yr"])
        else:
            return_used = normalize_return_percent_input(float(return_override_raw))

        rows.append(
            {
                "strategy_id": strategy_id,
                "strategy_name": strategy["name"],
                "strategy_value": round(strategy_value, 2),
                "return_used": round(return_used, 4),
            }
        )
    if not rows:
        raise ValueError("At least one active strategy is required.")
    return rows


def _parse_strategy_rows_for_edit(existing_rows: list[Any], form_data: Any) -> list[dict]:
    rows: list[dict] = []
    for row in existing_rows:
        strategy_id = int(row["strategy_id"])
        strategy_name = row["strategy_name"]
        value_raw = form_data.get(f"strategy_value_{strategy_id}", "").strip()
        return_raw = form_data.get(f"return_percent_{strategy_id}", "").strip()
        if value_raw == "" or return_raw == "":
            raise ValueError(f"Strategy value and return are required for {strategy_name}.")
        strategy_value = float(value_raw)
        if strategy_value < 0:
            raise ValueError(f"Strategy value must be non-negative for {strategy_name}.")
        return_used = normalize_return_percent_input(float(return_raw))
        rows.append(
            {
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "strategy_value": round(strategy_value, 2),
                "return_used": round(return_used, 4),
            }
        )
    return rows


def _build_snapshot_payload(form_data: Any, portfolio_id: int, strategy_rows: list[dict], buffer_1_percent: float, buffer_2_percent: float) -> dict:
    snapshot_date = form_data["snapshot_date"].strip()
    total_value = float(form_data["total_value"])
    actual_income = float(form_data["actual_income"])
    notes = form_data.get("notes", "").strip()

    if total_value <= 0:
        raise ValueError("Total portfolio value must be greater than zero.")
    if actual_income < 0:
        raise ValueError("Actual income must be zero or greater.")

    strategy_total = round(sum(float(row["strategy_value"]) for row in strategy_rows), 2)
    if abs(total_value - strategy_total) > TOTAL_TOLERANCE:
        raise ValueError(
            f"Total value ({total_value:.2f}) must match strategy sum ({strategy_total:.2f}) within {TOTAL_TOLERANCE:.2f}."
        )

    weighted_return = calculate_weighted_return(total_value, strategy_rows)
    income_metrics = calculate_income_metrics(total_value, weighted_return)
    buffer_values = calculate_buffer_values(income_metrics["msfi"], buffer_1_percent, buffer_2_percent)
    risk_status = calculate_risk_status(
        income_metrics["msfi"],
        actual_income,
        buffer_values["buffer_1_value"],
        buffer_values["buffer_2_value"],
    )

    return {
        "portfolio_id": portfolio_id,
        "snapshot_date": snapshot_date,
        "total_value": round(total_value, 2),
        "weighted_return": round(weighted_return, 4),
        "annual_earnings": income_metrics["annual_earnings"],
        "msfi": income_metrics["msfi"],
        "buffer_1_percent": round(buffer_1_percent, 6),
        "buffer_2_percent": round(buffer_2_percent, 6),
        "buffer_1_value": buffer_values["buffer_1_value"],
        "buffer_2_value": buffer_values["buffer_2_value"],
        "actual_income": round(actual_income, 2),
        "risk_status": risk_status,
        "notes": notes,
    }


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    @app.context_processor
    def inject_template_helpers():
        portfolios = get_all_portfolios()
        selected_portfolio_id = request.args.get("portfolio_id", type=int)
        if selected_portfolio_id is None and portfolios:
            selected_portfolio_id = int(portfolios[0]["id"])
        return {
            "nav_portfolios": portfolios,
            "nav_selected_portfolio_id": selected_portfolio_id,
            "risk_explanation": _risk_explanation,
        }

    @app.teardown_appcontext
    def _close_db(error=None):
        close_db(error)

    @app.cli.command("init-db")
    def init_db_command():
        with app.app_context():
            init_db()
        print("Database initialized.")

    @app.route("/")
    def dashboard():
        portfolios = get_all_portfolios()
        sections: list[dict] = []
        for portfolio in portfolios:
            portfolio_id = int(portfolio["id"])
            latest = get_latest_snapshot_by_portfolio(portfolio_id)
            latest_strategy_rows = []
            if latest is not None:
                latest_strategy_rows = [dict(row) for row in get_snapshot_strategy_rows(int(latest["id"]))]
                for row in latest_strategy_rows:
                    value = float(row["strategy_value"])
                    total = float(latest["total_value"])
                    weight = (value / total) if total > 0 else 0.0
                    row["weight_percent"] = round(weight * 100, 2)

            chart_rows = get_chart_snapshots_by_portfolio(portfolio_id)
            chart_data = {
                "labels": [row["snapshot_date"] for row in chart_rows],
                "portfolio_values": [float(row["total_value"]) for row in chart_rows],
                "msfi_values": [float(row["msfi"]) for row in chart_rows],
                "actual_income_values": [float(row["actual_income"]) for row in chart_rows],
            }
            sections.append(
                {
                    "portfolio": dict(portfolio),
                    "latest": dict(latest) if latest is not None else None,
                    "latest_strategy_rows": latest_strategy_rows,
                    "chart_data": chart_data,
                }
            )

        return render_template("dashboard.html", sections=sections, focus_portfolio_id=request.args.get("focus_portfolio_id", type=int))

    @app.route("/portfolios", methods=["GET", "POST"])
    def portfolios():
        error = None
        form_data = _portfolio_create_form_defaults()
        if request.method == "POST":
            form_data = _portfolio_create_form_from_request()
            try:
                if not form_data["name"]:
                    raise ValueError("Portfolio name is required.")
                b1, b2 = _parse_buffer_pair(form_data["buffer_1_percent"], form_data["buffer_2_percent"])
                create_portfolio(form_data["name"], b1, b2)
                return redirect(url_for("portfolios"))
            except (ValueError, sqlite3.IntegrityError) as exc:
                error = str(exc)
        return render_template("portfolios.html", portfolios=get_all_portfolios(), form_data=form_data, error=error)

    @app.route("/portfolios/<int:portfolio_id>/edit", methods=["GET", "POST"])
    def edit_portfolio(portfolio_id: int):
        portfolio = get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            abort(404)

        error = None
        form_data = _portfolio_edit_form_from_portfolio(portfolio)
        if request.method == "POST":
            form_data = _portfolio_edit_form_from_request()
            try:
                if not form_data["name"]:
                    raise ValueError("Portfolio name is required.")
                b1, b2 = _parse_buffer_pair(form_data["buffer_1_percent"], form_data["buffer_2_percent"])
                update_portfolio(portfolio_id, form_data["name"], b1, b2)
                return redirect(url_for("portfolios"))
            except (ValueError, sqlite3.IntegrityError) as exc:
                error = str(exc)

        return render_template(
            "edit_portfolio.html",
            portfolio=portfolio,
            form_data=form_data,
            error=error,
            snapshot_count=portfolio_snapshot_count(portfolio_id),
        )

    @app.route("/portfolios/<int:portfolio_id>/delete", methods=["POST"])
    def remove_portfolio(portfolio_id: int):
        deleted = delete_portfolio_if_empty(portfolio_id)
        if not deleted:
            return redirect(url_for("edit_portfolio", portfolio_id=portfolio_id, error="has_snapshots"))
        return redirect(url_for("portfolios"))

    @app.route("/portfolios/<int:portfolio_id>/strategies", methods=["GET", "POST"])
    def strategies(portfolio_id: int):
        portfolio = get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            abort(404)

        error = None
        form_data = _strategy_create_form_defaults()
        if request.method == "POST":
            form_data = _strategy_create_form_from_request()
            try:
                if not form_data["name"]:
                    raise ValueError("Strategy name is required.")
                default_return = normalize_return_percent_input(float(form_data["default_return_5yr_percent"]))
                create_strategy(portfolio_id, form_data["name"], round(default_return, 4), int(form_data["active_flag"]))
                return redirect(url_for("strategies", portfolio_id=portfolio_id))
            except (ValueError, sqlite3.IntegrityError) as exc:
                error = str(exc)

        strategy_rows = get_strategies_by_portfolio(portfolio_id, include_inactive=True)
        usage_map = {int(s["id"]): strategy_usage_count(int(s["id"])) for s in strategy_rows}
        return render_template(
            "strategies.html",
            portfolio=portfolio,
            strategies=strategy_rows,
            strategy_usage=usage_map,
            error=error,
            form_data=form_data,
        )

    @app.route("/strategies/<int:strategy_id>/edit", methods=["GET", "POST"])
    def edit_strategy(strategy_id: int):
        strategy = get_strategy_by_id(strategy_id)
        if strategy is None:
            abort(404)

        error = None
        form_data = _strategy_edit_form_from_strategy(strategy)
        if request.method == "POST":
            form_data = _strategy_edit_form_from_request()
            try:
                if not form_data["name"]:
                    raise ValueError("Strategy name is required.")
                default_return = normalize_return_percent_input(float(form_data["default_return_5yr_percent"]))
                update_strategy(strategy_id, form_data["name"], round(default_return, 4), int(form_data["active_flag"]))
                return redirect(url_for("strategies", portfolio_id=strategy["portfolio_id"]))
            except (ValueError, sqlite3.IntegrityError) as exc:
                error = str(exc)

        return render_template(
            "edit_strategy.html",
            strategy=strategy,
            form_data=form_data,
            error=error,
            usage_count=strategy_usage_count(strategy_id),
        )

    @app.route("/strategies/<int:strategy_id>/delete", methods=["POST"])
    def remove_strategy(strategy_id: int):
        strategy = get_strategy_by_id(strategy_id)
        if strategy is None:
            abort(404)
        deleted = delete_strategy_if_unused(strategy_id)
        if not deleted:
            return redirect(url_for("strategies", portfolio_id=strategy["portfolio_id"], error="in_use"))
        return redirect(url_for("strategies", portfolio_id=strategy["portfolio_id"]))

    @app.route("/add", methods=["GET", "POST"])
    def add_snapshot():
        portfolio_id = request.values.get("portfolio_id", type=int) or _active_portfolio_id()
        if portfolio_id is None:
            return redirect(url_for("portfolios"))
        portfolio = get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            abort(404)

        active_strategies = get_strategies_by_portfolio(portfolio_id, include_inactive=False)
        if not active_strategies:
            return redirect(url_for("strategies", portfolio_id=portfolio_id))

        error = None
        form_data = _snapshot_form_defaults()
        if request.method == "POST":
            form_data = dict(request.form)
            try:
                strategy_rows = _parse_strategy_rows_for_new_snapshot(active_strategies, request.form)
                payload = _build_snapshot_payload(
                    request.form,
                    portfolio_id,
                    strategy_rows,
                    float(portfolio["buffer_1_percent"]),
                    float(portfolio["buffer_2_percent"]),
                )
                insert_snapshot_with_strategies(payload, strategy_rows)
                return redirect(url_for("history", portfolio_id=portfolio_id))
            except (ValueError, KeyError) as exc:
                error = str(exc)

        return render_template(
            "add_snapshot.html",
            portfolio=portfolio,
            strategies=active_strategies,
            form_data=form_data,
            error=error,
            cancel_url=url_for("history", portfolio_id=portfolio_id),
        )

    @app.route("/edit/<int:snapshot_id>", methods=["GET", "POST"])
    def edit_snapshot(snapshot_id: int):
        snapshot = get_snapshot_by_id(snapshot_id)
        if snapshot is None:
            abort(404)

        strategy_rows = get_snapshot_strategy_rows(snapshot_id)
        error = None
        form_data = _snapshot_form_from_snapshot(snapshot)
        if request.method == "POST":
            form_data = dict(request.form)
            try:
                b1, b2 = _parse_buffer_pair(request.form["buffer_1_percent"], request.form["buffer_2_percent"])
                parsed_rows = _parse_strategy_rows_for_edit(strategy_rows, request.form)
                payload = _build_snapshot_payload(
                    request.form,
                    int(snapshot["portfolio_id"]),
                    parsed_rows,
                    b1,
                    b2,
                )
                update_snapshot_with_strategies(snapshot_id, payload, parsed_rows)
                return redirect(url_for("history", portfolio_id=snapshot["portfolio_id"]))
            except (ValueError, KeyError) as exc:
                error = str(exc)

        strategy_view_rows = []
        for row in strategy_rows:
            strategy_view_rows.append(
                {
                    "strategy_id": row["strategy_id"],
                    "strategy_name": row["strategy_name"],
                    "active_flag": row["active_flag"],
                    "strategy_value": row["strategy_value"],
                    "return_percent": round(float(row["return_used"]) * 100, 4),
                }
            )

        return render_template(
            "edit_snapshot.html",
            snapshot=snapshot,
            strategy_rows=strategy_view_rows,
            form_data=form_data,
            error=error,
            cancel_url=url_for("history", portfolio_id=snapshot["portfolio_id"]),
        )

    @app.route("/delete/<int:snapshot_id>", methods=["POST"])
    def remove_snapshot(snapshot_id: int):
        snapshot = get_snapshot_by_id(snapshot_id)
        if snapshot is None:
            abort(404)
        delete_snapshot(snapshot_id)
        return redirect(_safe_next_path(request.form.get("next")))

    @app.route("/history")
    def history():
        portfolio_id = request.args.get("portfolio_id", type=int) or _active_portfolio_id()
        if portfolio_id is None:
            return render_template("history.html", portfolio=None, snapshots=[], snapshot_details={})
        portfolio = get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            abort(404)

        snapshots = get_snapshots_by_portfolio(portfolio_id)
        snapshot_details = {}
        for row in snapshots:
            snapshot_details[int(row["id"])] = get_snapshot_strategy_rows(int(row["id"]))
        return render_template(
            "history.html",
            portfolio=portfolio,
            snapshots=snapshots,
            snapshot_details=snapshot_details,
        )

    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
