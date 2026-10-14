"""Deterministic planning comparison for explicitly supplied loan terms."""
from __future__ import annotations

import math
from typing import Any


METHOD = "FIXED_RATE_NOMINAL_ANNUAL_MONTHLY_REPAYMENT_V1"


def compare_repayment_tenures(
    *, principal: float, annual_interest_rate_percent: float, fees: float,
    monthly_income: float, monthly_expenses: float, existing_monthly_obligations: float,
    max_debt_to_income_ratio: float, tenures_months: list[int],
) -> dict[str, Any]:
    values = (principal, annual_interest_rate_percent, fees, monthly_income, monthly_expenses,
              existing_monthly_obligations, max_debt_to_income_ratio)
    if any(not math.isfinite(float(value)) for value in values):
        raise ValueError("All amounts and rates must be finite numbers")
    if principal <= 0 or not 0 <= annual_interest_rate_percent <= 100:
        raise ValueError("Principal must be positive and annual interest must be between 0% and 100%")
    if fees < 0 or monthly_income <= 0 or monthly_expenses < 0 or existing_monthly_obligations < 0:
        raise ValueError("Fees, expenses, and existing obligations cannot be negative; income must be positive")
    if not 0 < max_debt_to_income_ratio <= 1:
        raise ValueError("The explicit affordability limit must be greater than 0 and at most 1")
    if not tenures_months or len(tenures_months) > 24 or any(type(term) is not int or not 1 <= term <= 360 for term in tenures_months):
        raise ValueError("Supply 1–24 unique tenures from 1 to 360 months")
    if len(set(tenures_months)) != len(tenures_months):
        raise ValueError("Tenures must be unique")

    monthly_rate = annual_interest_rate_percent / 1200
    comparisons = []
    for months in sorted(tenures_months):
        if monthly_rate == 0:
            installment = principal / months
        else:
            factor = (1 + monthly_rate) ** months
            installment = principal * monthly_rate * factor / (factor - 1)
        scheduled_repayment = installment * months
        total_interest = scheduled_repayment - principal
        total_cost = scheduled_repayment + fees
        total_monthly_debt = existing_monthly_obligations + installment
        dti = total_monthly_debt / monthly_income
        residual = monthly_income - monthly_expenses - total_monthly_debt
        affordable = dti <= max_debt_to_income_ratio and residual >= 0
        comparisons.append({
            "tenure_months": months,
            "monthly_installment": round(installment, 2),
            "scheduled_total_repayment": round(scheduled_repayment, 2),
            "total_interest": round(max(total_interest, 0), 2),
            "fees": round(fees, 2),
            "total_cost_including_fees": round(total_cost, 2),
            "monthly_debt_to_income_ratio": round(dti, 4),
            "monthly_residual_after_expenses_and_debt": round(residual, 2),
            "affordable_under_supplied_constraints": affordable,
        })
    eligible = [item for item in comparisons if item["affordable_under_supplied_constraints"]]
    recommended = min(eligible, key=lambda item: (item["total_cost_including_fees"], item["tenure_months"])) if eligible else None
    return {
        "status": "COMPARISON_AVAILABLE" if eligible else "NO_TENURE_MEETS_SUPPLIED_CONSTRAINTS",
        "method": METHOD,
        "interest_convention": "Nominal annual rate divided by 12; fixed monthly reducing-balance amortization; payments at month end.",
        "input_provenance": "All principal, rate, fees, income, expenses, obligations, and affordability limit were explicitly supplied for this hypothetical. They are not independently verified.",
        "recommendation": ({"tenure_months": recommended["tenure_months"],
            "reason": "Lowest total repayment cost among the supplied tenures that meet the supplied debt-to-income limit and leave nonnegative monthly residual."} if recommended else None),
        "comparisons": comparisons,
        "decision_use": "HYPOTHETICAL_PLANNING_ONLY_NOT_A_SCORE_OR_LENDING_DECISION",
        "persisted": False,
    }
