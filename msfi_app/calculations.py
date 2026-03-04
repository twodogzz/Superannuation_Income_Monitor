"""Pure financial calculation functions for multi-portfolio MSFI monitoring."""

from __future__ import annotations


def _round_money(value: float) -> float:
    """Round monetary values to 2 decimal places."""
    return round(value, 2)


def _round_return(value: float) -> float:
    """Round return values to 4 decimal places."""
    return round(value, 4)


def normalize_return_percent_input(percent_value: float) -> float:
    """Convert percent input (for example 6.5) to decimal return (0.065)."""
    value = float(percent_value)
    if value < -100.0 or value > 1000.0:
        raise ValueError("Return percentage must be between -100 and 1000.")
    return value / 100.0


def calculate_weighted_return(total_value: float, strategy_rows: list[dict]) -> float:
    """
    Weighted Return = sum((strategy_value / total_value) * return_used).

    `return_used` must be decimal form.
    """
    if total_value <= 0:
        raise ValueError("Total value must be greater than zero.")

    weighted = 0.0
    for row in strategy_rows:
        strategy_value = float(row["strategy_value"])
        return_used = float(row["return_used"])
        weighted += (strategy_value / total_value) * return_used
    return _round_return(weighted)


def calculate_income_metrics(total_value: float, weighted_return: float) -> dict[str, float]:
    """
    Calculate annual earnings and maximum sustainable fortnightly income.

    - Annual Earnings = total_value * weighted_return
    - MSFI = annual_earnings / 26
    """
    annual_earnings = total_value * weighted_return
    msfi = annual_earnings / 26.0
    return {
        "annual_earnings": _round_money(annual_earnings),
        "msfi": _round_money(msfi),
    }


def calculate_buffer_values(msfi: float, buffer_1_percent: float, buffer_2_percent: float) -> dict[str, float]:
    """
    Calculate buffer values from stored percentages.

    Input percentages are decimals (for example, 0.10 for 10%).
    """
    buffer_1_value = msfi * (1.0 - buffer_1_percent)
    buffer_2_value = msfi * (1.0 - buffer_2_percent)
    return {
        "buffer_1_value": _round_money(buffer_1_value),
        "buffer_2_value": _round_money(buffer_2_value),
    }


def calculate_risk_status(msfi: float, actual_income: float, buffer_1_value: float, buffer_2_value: float) -> str:
    """
    Determine risk state from stored snapshot thresholds.

    - actual > msfi: Overdrawing
    - actual > buffer_1_value: Alert
    - actual > buffer_2_value: Caution
    - else: Safe
    """
    if actual_income > msfi:
        return "Overdrawing"
    if actual_income > buffer_1_value:
        return "Alert"
    if actual_income > buffer_2_value:
        return "Caution"
    return "Safe"
