"""Transparent, non-PD bank cash-flow index (independent of Phase 2F)."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


INDEX_VERSION = "BANK_FINANCIAL_HEALTH_INDEX_V1"
ASSESSMENT_TYPE = "BANK_CASHFLOW_EXPERIMENTAL"
WEIGHTS = {
    "surplus_month_rate": 0.25,
    "expense_to_income": 0.25,
    "income_regularity": 0.20,
    "liquidity_buffer": 0.15,
    "debt_burden": 0.15,
}
MINIMUM_COMPLETE_MONTHS = 3


def _score(features: dict[str, float | None]) -> dict[str, Any]:
    # Debt is unknown unless explicitly identified; remaining weights are normalized.
    available = {name: value for name, value in features.items() if value is not None}
    weight_total = sum(WEIGHTS[name] for name in available)
    if weight_total <= 0:
        return {"score": None, "normalized_health": None, "contributions": []}
    contributions = []
    health = 0.0
    for name, value in available.items():
        normalized_weight = WEIGHTS[name] / weight_total
        component = float(np.clip(value, 0.0, 1.0))
        points = 600 * normalized_weight * component
        health += normalized_weight * component
        contributions.append({"feature": name, "value": round(component, 6),
                              "weight": round(normalized_weight, 6),
                              "score_contribution": round(points, 2),
                              "direction": "FAVORABLE" if component >= 0.5 else "ADVERSE"})
    score = round(300 + 600 * health)
    # Ensure rounding never creates a mismatch in reported arithmetic.
    diff = score - 300 - sum(x["score_contribution"] for x in contributions)
    if contributions:
        contributions[-1]["score_contribution"] = round(contributions[-1]["score_contribution"] + diff, 2)
    return {"score": int(score), "normalized_health": round(health, 6), "contributions": contributions}


def score_observed_month(income_total: float, expense_total: float,
                         average_balance: float | None, debt_burden: float | None = None) -> dict[str, Any]:
    """Score patterns visible in one month, omitting features needing longer history."""
    income, expense = float(income_total), float(expense_total)
    features = {
        "surplus_month_rate": float(income > expense),
        "expense_to_income": float(np.clip(1 - expense / income, 0, 1)) if income > 0 else None,
        "income_regularity": None,
        "liquidity_buffer": (float(np.clip(float(average_balance) / (3 * expense), 0, 1))
            if average_balance is not None and expense > 0 else None),
        "debt_burden": debt_burden,
    }
    available = sum(value is not None for value in features.values())
    score = _score(features)["score"] if available >= 2 else None
    return {"score": score, "available_pattern_count": available, "feature_values": features}


def _parse_statement_dates(values: pd.Series) -> pd.Series:
    raw = values.astype(str).str.strip()
    parsed = pd.to_datetime(raw, errors="coerce", dayfirst=True)
    iso = raw.str.match(r"^\d{4}-\d{2}-\d{2}(?:$|T)")
    if iso.any():
        parsed.loc[iso] = pd.to_datetime(raw.loc[iso], errors="coerce", format="mixed")
    return parsed


def calculate_bank_health_index(transactions: pd.DataFrame, *, currency: str | None = None,
                                 evidence: dict | None = None) -> dict[str, Any]:
    """Calculate the fixed V1 index only for adequately covered, coherent evidence."""
    evidence = evidence or {}
    required = {"date", "amount", "type"}
    gaps: list[str] = []
    if transactions is None or transactions.empty or not required.issubset(transactions.columns):
        transactions = pd.DataFrame(columns=list(required))
        gaps.append("NO_VALIDATED_TRANSACTIONS")
    df = transactions.copy()
    df["date"] = _parse_statement_dates(df["date"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
    df["type"] = df["type"].astype(str).str.upper().str.strip()
    df = df[df.date.notna() & df.amount.notna() & df.type.isin(["CR", "DR"])].copy()
    months = sorted(df.date.dt.to_period("M").astype(str).unique().tolist()) if not df.empty else []
    if len(months) < MINIMUM_COMPLETE_MONTHS:
        gaps.append("AT_LEAST_3_COMPLETE_CALENDAR_MONTHS_REQUIRED")
    if months:
        expected = pd.period_range(months[0], months[-1], freq="M").astype(str).tolist()
        if months != expected:
            gaps.append("NONCONSECUTIVE_OBSERVATION_MONTHS")
    if not evidence.get("account_linked", False):
        gaps.append("ACCOUNT_REFERENCE_NOT_VERIFIED_ACROSS_STATEMENTS")
    if not currency:
        gaps.append("CURRENCY_NOT_CONFIRMED")
    if evidence.get("balance_reconciled") is not True:
        gaps.append("RUNNING_BALANCE_RECONCILIATION_NOT_VERIFIED")
    if evidence.get("duplicate_ambiguity", False):
        gaps.append("DUPLICATE_TRANSACTIONS_REQUIRE_REVIEW")
    if evidence.get("page_coverage_complete") is not True:
        gaps.append("STATEMENT_PAGE_COVERAGE_NOT_VERIFIED")
    if evidence.get("complete_month_coverage") is not True:
        gaps.append("COMPLETE_CALENDAR_MONTH_COVERAGE_NOT_VERIFIED")
    if evidence.get("transaction_order_valid") is not True:
        gaps.append("TRANSACTION_ORDER_NOT_VERIFIED")
    if evidence.get("non_cashflow_adjustments_clear") is not True:
        gaps.append("TRANSFER_REFUND_OR_REVERSAL_REVIEW_REQUIRED")
    if float(evidence.get("extraction_quality_min", 1.0) or 0.0) < 0.80:
        gaps.append("EXTRACTION_QUALITY_BELOW_80_PERCENT")

    if not df.empty:
        df["month"] = df.date.dt.to_period("M").astype(str)
        monthly = []
        for month in months:
            part = df[df.month == month]
            credit = float(part.loc[part.type == "CR", "amount"].sum())
            debit = float(part.loc[part.type == "DR", "amount"].sum())
            month_balances = pd.to_numeric(part.get("closing_balance", pd.Series(dtype=float)), errors="coerce").dropna()
            month_descriptions = part.get("narration", pd.Series("", index=part.index)).fillna("").astype(str)
            month_debt_rows = part.type.eq("DR") & month_descriptions.str.contains(
                r"\b(?:emi|loan repayment|loan instal+ment|loan installment|nach loan|ecs loan)\b", case=False, regex=True)
            debt_burden = (float(np.clip(1 - float(part.loc[month_debt_rows, "amount"].sum()) / credit, 0, 1))
                if month_debt_rows.any() and credit > 0 else None)
            month_score = score_observed_month(credit, debit,
                float(month_balances.mean()) if not month_balances.empty else None, debt_burden)
            monthly.append({"month": month, "income_total": round(credit, 2),
                            "expense_total": round(debit, 2), "net_flow": round(credit-debit, 2),
                            "credit_count": int((part.type == "CR").sum()),
                            "debit_count": int((part.type == "DR").sum()),
                            "observed_pattern_score": month_score["score"],
                            "available_pattern_count": month_score["available_pattern_count"],
                            "average_balance": round(float(month_balances.mean()), 2) if not month_balances.empty else None})
        credits = sum(x["income_total"] for x in monthly)
        debits = sum(x["expense_total"] for x in monthly)
        income_per_month = credits / len(monthly) if monthly else 0
        expense_per_month = debits / len(monthly) if monthly else 0
        surplus_rate = sum(x["net_flow"] > 0 for x in monthly) / len(monthly) if monthly else None
        expense_ratio = (float(np.clip(1 - debits / credits, 0, 1)) if credits > 0 else None)
        monthly_income = np.asarray([x["income_total"] for x in monthly], dtype=float)
        cv = (float(np.std(monthly_income, ddof=1) / np.mean(monthly_income))
              if len(monthly_income) >= 2 and np.mean(monthly_income) > 0 else None)
        regularity = float(1 / (1 + max(cv, 0))) if cv is not None else None
        balances = pd.to_numeric(df.get("closing_balance", pd.Series(dtype=float)), errors="coerce").dropna()
        liquidity = (float(np.clip(balances.mean() / (3 * expense_per_month), 0, 1))
                     if not balances.empty and expense_per_month > 0 else None)
        descriptions = df.get("narration", pd.Series("", index=df.index)).fillna("").astype(str)
        explicit_debt = df.type.eq("DR") & descriptions.str.contains(
            r"\b(?:emi|loan repayment|loan instal+ment|loan installment|nach loan|ecs loan)\b", case=False, regex=True)
        identified_debt = float(df.loc[explicit_debt, "amount"].sum() / max(len(monthly), 1))
        debt_burden = (float(np.clip(1 - identified_debt / income_per_month, 0, 1))
                       if explicit_debt.any() and income_per_month > 0 else None)
        average_balance = round(float(balances.mean()), 2) if not balances.empty else None
        features = {"surplus_month_rate": surplus_rate, "expense_to_income": expense_ratio,
                    "income_regularity": regularity, "liquidity_buffer": liquidity,
                    "debt_burden": debt_burden}
        scored = _score(features) if not gaps else {"score": None, "normalized_health": None, "contributions": []}
        reasons = [dict(x, explanation=("Higher is favorable; this component raises the index." if x["direction"] == "FAVORABLE"
                   else "Lower is adverse; this component reduces the index.")) for x in scored["contributions"]]
        return {
            "assessment_type": ASSESSMENT_TYPE, "model_name": "Experimental Bank Financial Health Index",
            "model_version": INDEX_VERSION, "status": "SCORED" if scored["score"] is not None else "INSUFFICIENT_EVIDENCE",
            "scoreable": scored["score"] is not None, "score": scored["score"], "pd": None,
            "risk_tier": None, "currency": currency, "months_observed": len(months),
            "observed_months": months, "transaction_count": len(df), "monthly": monthly,
            "financial_metrics": {"average_monthly_income": round(income_per_month, 2),
                "average_monthly_expenses": round(expense_per_month, 2),
                "monthly_income_coefficient_of_variation": round(cv, 6) if cv is not None else None,
                "average_observed_closing_balance": average_balance,
                "minimum_observed_closing_balance": round(float(balances.min()), 2) if not balances.empty else None,
                "identified_monthly_debt_payments": round(identified_debt, 2) if explicit_debt.any() else None},
            "feature_values": {k: (round(float(v), 6) if v is not None else None) for k,v in features.items()},
            "feature_contributions": reasons, "reason_codes": [x["feature"] for x in reasons if x["direction"] == "ADVERSE"],
            "evidence_gaps": sorted(set(gaps)), "validation_status": "VALIDATED" if not gaps else "INCOMPLETE",
            "evidence": evidence,
            "methodology": {"mapping": "score = round(300 + 600 × normalized weighted health)",
                "weights": WEIGHTS, "minimum_history_months": MINIMUM_COMPLETE_MONTHS,
                "missing_data_policy": "Each unavailable indicator is omitted and remaining fixed weights are renormalized; an unobserved debt indicator is unknown, not zero.",
                "limitations": ["This is an experimental descriptive index, not a validated credit score or PD.",
                    "No lending tier, bureau equivalence, or lending decision is produced.",
                    "Keyword detected repayments are unverified; absent matches do not mean no debt."]},
            "recommendations": _recommendations(features),
        }
    return {"assessment_type": ASSESSMENT_TYPE, "model_name": "Experimental Bank Financial Health Index",
        "model_version": INDEX_VERSION, "status": "INSUFFICIENT_EVIDENCE", "scoreable": False,
        "score": None, "pd": None, "risk_tier": None, "currency": currency,
        "months_observed": len(months), "observed_months": months, "transaction_count": len(df),
        "monthly": [], "feature_values": {}, "feature_contributions": [], "reason_codes": [],
        "evidence_gaps": sorted(set(gaps)), "validation_status": "INCOMPLETE", "evidence": evidence,
        "methodology": {"minimum_history_months": MINIMUM_COMPLETE_MONTHS, "weights": WEIGHTS,
            "limitations": ["Experimental non-PD financial-health index; insufficient evidence for a score."]},
        "recommendations": ["Provide complete, consecutive monthly statements for one verified account."]}


def _recommendations(features: dict[str, float | None]) -> list[str]:
    result = []
    if features.get("expense_to_income") is not None and features["expense_to_income"] < .5:
        result.append("Review recurring spending and preserve a monthly cash-flow surplus where feasible.")
    if features.get("income_regularity") is not None and features["income_regularity"] < .6:
        result.append("Maintain a cash buffer for months with lower observed inflows.")
    if features.get("liquidity_buffer") is not None and features["liquidity_buffer"] < .5:
        result.append("Build a reserve relative to observed monthly outflows where feasible.")
    if not result:
        result.append("Review the underlying monthly figures; this descriptive index does not predict repayment outcomes.")
    return result


def simulate_bank_health(baseline: dict, scenario: dict[str, float]) -> dict:
    """Hypothetical same-formula scenario; leaves original assessment untouched."""
    allowed = {"monthly_income", "monthly_expenses", "monthly_debt_obligations", "average_balance", "income_volatility"}
    if set(scenario) - allowed or not scenario:
        raise ValueError("Provide supported scenario fields only")
    for name, value in scenario.items():
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite non-negative number")
    current = baseline.get("feature_values") or {}
    monthly = baseline.get("monthly", [])
    metrics = baseline.get("financial_metrics", {})
    income = float(scenario.get("monthly_income", metrics.get("average_monthly_income", np.mean([x["income_total"] for x in monthly]) if monthly else 0)))
    expenses = float(scenario.get("monthly_expenses", metrics.get("average_monthly_expenses", np.mean([x["expense_total"] for x in monthly]) if monthly else 0)))
    debt = float(scenario.get("monthly_debt_obligations", metrics.get("identified_monthly_debt_payments") or 0))
    balance = float(scenario.get("average_balance", metrics.get("average_observed_closing_balance") or 0))
    volatility = min(float(scenario.get("income_volatility", metrics.get("monthly_income_coefficient_of_variation") or 0)), .99)
    if debt > expenses:
        raise ValueError("Monthly debt obligations cannot exceed monthly expenses")
    income_sequence = [income * (1-volatility), income, income * (1+volatility)]
    synthetic_features = {
        "surplus_month_rate": sum(value > expenses for value in income_sequence) / 3,
        "expense_to_income": float(np.clip(1 - expenses / income, 0, 1)) if income > 0 else 0.0,
        "income_regularity": 1 / (1 + volatility),
        "liquidity_buffer": float(np.clip(balance / (3 * expenses), 0, 1)) if expenses > 0 else (1.0 if balance > 0 else 0.0),
        "debt_burden": float(np.clip(1 - debt / income, 0, 1)) if ("monthly_debt_obligations" in scenario or current.get("debt_burden") is not None) and income > 0 else current.get("debt_burden"),
    }
    score = _score(synthetic_features)
    return {"hypothetical_only": True, "score": score["score"], "pd": None,
        "original_score": baseline.get("score"), "score_delta": (score["score"] - baseline["score"] if score["score"] is not None and baseline.get("score") is not None else None),
        "feature_values": synthetic_features, "feature_contributions": score["contributions"],
        "recommendations": _recommendations(synthetic_features), "model_version": INDEX_VERSION}
