"""Pure financial calculation functions for multi-portfolio MSFI monitoring."""

from __future__ import annotations


def _round_money(value: float) -> float:
    """Round monetary values to 2 decimal places."""
    return round(value, 2)


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
    - actual > lower of the two buffer values: Caution
    - else: Safe
    """
    caution_threshold = min(buffer_1_value, buffer_2_value)
    if actual_income > msfi:
        return "Overdrawing"
    if actual_income > caution_threshold:
        return "Caution"
    return "Safe"
