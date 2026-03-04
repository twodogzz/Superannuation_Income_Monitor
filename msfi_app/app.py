"""MSFI Monitoring Flask application with multi-portfolio support."""

from __future__ import annotations

import sqlite3
from typing import Any

from flask import Flask, abort, redirect, render_template, request, url_for

from calculations import calculate_buffer_values, calculate_income_metrics, calculate_risk_status
from config import Config
from database import close_db, init_db
from models import (
    create_portfolio,
    delete_snapshot,
    get_all_portfolios,
    get_chart_snapshots_by_portfolio,
    get_latest_snapshot_by_portfolio,
    get_portfolio_by_id,
    get_snapshot_by_id,
    get_snapshots_by_portfolio,
    insert_snapshot,
    update_portfolio_buffers,
    update_snapshot,
)


def _safe_next_path(next_path: str | None) -> str:
    """Allow only app-local redirect paths."""
    if next_path and next_path.startswith("/"):
        return next_path
    return url_for("dashboard")


def _percent_text(decimal_value: float) -> str:
    """Render decimal percentage as compact text (for example, 10%)."""
    percent = round(decimal_value * 100.0, 2)
    if percent.is_integer():
        return f"{int(percent)}%"
    return f"{percent}%"


def _risk_explanation(risk_status: str, buffer_1_percent: float, buffer_2_percent: float) -> str:
    """Build explanation text using stored snapshot buffer percentages."""
    conservative_buffer = max(buffer_1_percent, buffer_2_percent)
    conservative_label = _percent_text(conservative_buffer)
    if risk_status == "Overdrawing":
        return "Actual income is above MSFI"
    if risk_status == "Caution":
        return f"Actual income is above {conservative_label} buffer"
    return f"Actual income is below {conservative_label} buffer"


def _parse_percent_input(raw_value: str) -> float:
    """
    Parse percent text from form into decimal representation.

    Example: input 10 -> 0.10
    """
    percent = float(raw_value)
    decimal = percent / 100.0
    if decimal < 0 or decimal >= 1:
        raise ValueError("Buffer percentages must be between 0 and 99.99.")
    return decimal


def _active_portfolio_id() -> int | None:
    """Select current portfolio from query param, falling back to first portfolio."""
    portfolios = get_all_portfolios()
    if not portfolios:
        return None

    requested_id = request.args.get("portfolio_id", type=int)
    if requested_id is not None:
        for portfolio in portfolios:
            if int(portfolio["id"]) == requested_id:
                return requested_id
    return int(portfolios[0]["id"])


def _build_snapshot_from_form(form_data: Any, buffer_1_percent: float, buffer_2_percent: float, portfolio_id: int) -> dict:
    """Parse form data and return a calculated snapshot row payload."""
    snapshot_date = form_data["snapshot_date"].strip()
    total_value = float(form_data["total_value"])
    weighted_return_percent = float(form_data["weighted_return_percent"])
    actual_income = float(form_data["actual_income"])
    notes = form_data.get("notes", "").strip()

    if total_value <= 0:
        raise ValueError("Total portfolio value must be greater than zero.")
    if actual_income < 0:
        raise ValueError("Actual income must be zero or greater.")

    weighted_return = weighted_return_percent / 100.0
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
        "weighted_return": round(weighted_return, 6),
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


def create_app() -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(Config)

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
        """Initialize SQLite schema."""
        with app.app_context():
            init_db()
        print("Database initialized.")

    @app.route("/")
    def dashboard():
        portfolios = get_all_portfolios()
        sections = []
        for portfolio in portfolios:
            portfolio_id = int(portfolio["id"])
            latest = get_latest_snapshot_by_portfolio(portfolio_id)
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
                    "chart_data": chart_data,
                }
            )

        return render_template("dashboard.html", sections=sections, focus_portfolio_id=request.args.get("focus_portfolio_id", type=int))

    @app.route("/portfolios", methods=["GET", "POST"])
    def portfolios():
        error = None
        form_data = {"name": "", "buffer_1_percent": "10", "buffer_2_percent": "20"}

        if request.method == "POST":
            form_data = {
                "name": request.form.get("name", "").strip(),
                "buffer_1_percent": request.form.get("buffer_1_percent", "10").strip(),
                "buffer_2_percent": request.form.get("buffer_2_percent", "20").strip(),
            }
            try:
                if not form_data["name"]:
                    raise ValueError("Portfolio name is required.")
                buffer_1_percent = _parse_percent_input(form_data["buffer_1_percent"])
                buffer_2_percent = _parse_percent_input(form_data["buffer_2_percent"])
                create_portfolio(form_data["name"], buffer_1_percent, buffer_2_percent)
                return redirect(url_for("portfolios"))
            except (ValueError, sqlite3.IntegrityError) as exc:
                error = str(exc)

        return render_template("portfolios.html", portfolios=get_all_portfolios(), error=error, form_data=form_data)

    @app.route("/portfolios/<int:portfolio_id>/buffers", methods=["GET", "POST"])
    def edit_portfolio_buffers(portfolio_id: int):
        portfolio = get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            abort(404)

        error = None
        form_data = {
            "buffer_1_percent": str(round(float(portfolio["buffer_1_percent"]) * 100, 4)),
            "buffer_2_percent": str(round(float(portfolio["buffer_2_percent"]) * 100, 4)),
        }

        if request.method == "POST":
            form_data = {
                "buffer_1_percent": request.form.get("buffer_1_percent", "").strip(),
                "buffer_2_percent": request.form.get("buffer_2_percent", "").strip(),
            }
            try:
                buffer_1_percent = _parse_percent_input(form_data["buffer_1_percent"])
                buffer_2_percent = _parse_percent_input(form_data["buffer_2_percent"])
                update_portfolio_buffers(portfolio_id, buffer_1_percent, buffer_2_percent)
                return redirect(url_for("dashboard", focus_portfolio_id=portfolio_id))
            except ValueError as exc:
                error = str(exc)

        return render_template("edit_buffers.html", portfolio=portfolio, error=error, form_data=form_data)

    @app.route("/add", methods=["GET", "POST"])
    def add_snapshot():
        portfolio_id = request.values.get("portfolio_id", type=int)
        if portfolio_id is None:
            portfolio_id = _active_portfolio_id()

        if portfolio_id is None:
            return redirect(url_for("portfolios"))

        portfolio = get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            abort(404)

        error = None
        form_data = {
            "snapshot_date": "",
            "total_value": "",
            "weighted_return_percent": "",
            "actual_income": "",
            "notes": "",
        }

        if request.method == "POST":
            form_data = dict(request.form)
            try:
                snapshot = _build_snapshot_from_form(
                    request.form,
                    float(portfolio["buffer_1_percent"]),
                    float(portfolio["buffer_2_percent"]),
                    portfolio_id,
                )
                insert_snapshot(snapshot)
                return redirect(url_for("history", portfolio_id=portfolio_id))
            except (KeyError, ValueError) as exc:
                error = str(exc)

        return render_template(
            "add_snapshot.html",
            error=error,
            form_data=form_data,
            portfolio=portfolio,
            form_title="Add Snapshot",
            submit_label="Save Snapshot",
            cancel_url=url_for("history", portfolio_id=portfolio_id),
        )

    @app.route("/edit/<int:snapshot_id>", methods=["GET", "POST"])
    def edit_snapshot(snapshot_id: int):
        snapshot_row = get_snapshot_by_id(snapshot_id)
        if snapshot_row is None:
            abort(404)

        error = None
        form_data = {
            "snapshot_date": snapshot_row["snapshot_date"],
            "total_value": snapshot_row["total_value"],
            "weighted_return_percent": round(float(snapshot_row["weighted_return"]) * 100, 4),
            "actual_income": snapshot_row["actual_income"],
            "buffer_1_percent": round(float(snapshot_row["buffer_1_percent"]) * 100, 4),
            "buffer_2_percent": round(float(snapshot_row["buffer_2_percent"]) * 100, 4),
            "notes": snapshot_row["notes"] or "",
        }

        if request.method == "POST":
            form_data = dict(request.form)
            try:
                buffer_1_percent = _parse_percent_input(request.form["buffer_1_percent"])
                buffer_2_percent = _parse_percent_input(request.form["buffer_2_percent"])
                snapshot = _build_snapshot_from_form(request.form, buffer_1_percent, buffer_2_percent, int(snapshot_row["portfolio_id"]))
                update_snapshot(snapshot_id, snapshot)
                return redirect(url_for("history", portfolio_id=snapshot_row["portfolio_id"]))
            except (KeyError, ValueError) as exc:
                error = str(exc)

        return render_template(
            "edit_snapshot.html",
            error=error,
            form_data=form_data,
            snapshot=snapshot_row,
            form_title="Edit Snapshot",
            submit_label="Update Snapshot",
            cancel_url=url_for("history", portfolio_id=snapshot_row["portfolio_id"]),
        )

    @app.route("/delete/<int:snapshot_id>", methods=["POST"])
    def remove_snapshot(snapshot_id: int):
        snapshot_row = get_snapshot_by_id(snapshot_id)
        if snapshot_row is None:
            abort(404)
        delete_snapshot(snapshot_id)
        return redirect(_safe_next_path(request.form.get("next")))

    @app.route("/history")
    def history():
        portfolio_id = request.args.get("portfolio_id", type=int)
        if portfolio_id is None:
            portfolio_id = _active_portfolio_id()

        if portfolio_id is None:
            return render_template("history.html", snapshots=[], portfolio=None)

        portfolio = get_portfolio_by_id(portfolio_id)
        if portfolio is None:
            abort(404)

        snapshots = get_snapshots_by_portfolio(portfolio_id)
        return render_template("history.html", snapshots=snapshots, portfolio=portfolio)

    with app.app_context():
        init_db()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
