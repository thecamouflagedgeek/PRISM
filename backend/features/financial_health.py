"""Descriptive bank-statement indicators, independent of the frozen card scorecard."""
import re

import numpy as np
import pandas as pd


DEBT_TERMS = re.compile(r"\b(?:emi|loan|finance|nach|ecs|installment|instalment)\b", re.I)
RETURN_TERMS = re.compile(r"\b(?:returned|return|bounce[d]?|dishonou?red|reversal)\b", re.I)
SALARY_TERMS = re.compile(r"\b(?:salary|payroll|wages)\b", re.I)


def build_financial_health(transactions: pd.DataFrame | None, *, extraction: dict | None = None) -> dict:
    """Summarize validated transactions without retaining narration or customer identifiers."""
    extraction = extraction or {}
    base = {
        "status": "UNAVAILABLE", "source_type": "BANK_STATEMENT",
        "separate_from_frozen_credit_pd": True,
        "currency": None, "extraction_method": extraction.get("method") or extraction.get("extraction_method"),
        "page_count": extraction.get("page_count"), "transaction_count": 0,
        "months_observed": 0, "monthly": [], "cash_flow_variability": None,
        "average_observed_closing_balance": None,
        "recurring_obligation_patterns": {"pattern_count": 0, "matching_transaction_count": 0, "amount_total": 0.0},
        "possible_debt_payments": {"matching_transaction_count": 0, "amount_total": 0.0},
        "explicit_returned_payment_indicators": {"matching_transaction_count": 0, "amount_total": 0.0},
        "salary_labelled_credits": {"months": 0, "transaction_count": 0, "amount_total": 0.0},
        "limitations": ["Transaction descriptions are not retained in this summary.",
                        "Keyword indicators are leads for review, not verified obligations or income.",
                        "This panel is not a lending decision or credit-card default probability."],
    }
    required = {"date", "amount", "type"}
    if not isinstance(transactions, pd.DataFrame) or transactions.empty or not required.issubset(transactions.columns):
        return base

    df = transactions.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
    df["type"] = df["type"].astype(str).str.upper().str.strip()
    if "narration" not in df:
        df["narration"] = ""
    df["narration"] = df["narration"].fillna("").astype(str)
    df = df[df["date"].notna() & df["amount"].notna() & df["type"].isin(["CR", "DR"])].copy()
    if df.empty:
        return base

    df["month"] = df["date"].dt.strftime("%Y-%m")
    grouped = df.groupby("month", sort=True)
    monthly = []
    for month, rows in grouped:
        credits = rows.loc[rows["type"] == "CR", "amount"]
        debits = rows.loc[rows["type"] == "DR", "amount"]
        monthly.append({"month": month, "income_total": round(float(credits.sum()), 2),
                        "expense_total": round(float(debits.sum()), 2),
                        "net_flow": round(float(credits.sum() - debits.sum()), 2),
                        "credit_count": int(len(credits)), "debit_count": int(len(debits))})
    net = np.asarray([item["net_flow"] for item in monthly], dtype=float)
    variability = (float(np.std(net, ddof=1) / np.mean(np.abs(net)))
                   if len(net) >= 2 and np.mean(np.abs(net)) > 0 else None)

    narration = df["narration"]
    debt = df["type"].eq("DR") & narration.str.contains(DEBT_TERMS)
    returned = narration.str.contains(RETURN_TERMS)
    salary = df["type"].eq("CR") & narration.str.contains(SALARY_TERMS)
    # Only count exact normalized description repetition; never expose the descriptions.
    norm = narration.str.casefold().str.replace(r"[^a-z0-9]+", " ", regex=True).str.strip()
    recurring = df["type"].eq("DR") & norm.ne("")
    patterns = df.loc[recurring].assign(_description=norm[recurring]).groupby("_description").filter(
        lambda rows: rows["month"].nunique() >= 2)
    balances = pd.to_numeric(df.get("closing_balance", pd.Series(index=df.index, dtype=float)), errors="coerce").dropna()

    def tally(mask):
        rows = df.loc[mask]
        return {"matching_transaction_count": int(len(rows)), "amount_total": round(float(rows["amount"].sum()), 2)}

    salary_rows = df.loc[salary]
    base.update({"status": "AVAILABLE", "transaction_count": int(len(df)), "months_observed": len(monthly),
        "monthly": monthly, "cash_flow_variability": round(variability, 4) if variability is not None else None,
        "average_observed_closing_balance": round(float(balances.mean()), 2) if not balances.empty else None,
        "recurring_obligation_patterns": {"pattern_count": int(patterns["_description"].nunique()) if not patterns.empty else 0,
            "matching_transaction_count": int(len(patterns)), "amount_total": round(float(patterns["amount"].sum()), 2) if not patterns.empty else 0.0},
        "possible_debt_payments": tally(debt), "explicit_returned_payment_indicators": tally(returned),
        "salary_labelled_credits": {"months": int(salary_rows["month"].nunique()), "transaction_count": int(len(salary_rows)),
            "amount_total": round(float(salary_rows["amount"].sum()), 2)}})
    return base
