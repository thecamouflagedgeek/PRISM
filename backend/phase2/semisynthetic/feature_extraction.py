"""Transaction-derived Phase 2B behavioral features for real and synthetic ledgers.

The formulas intentionally mirror the corrected Phase 2A Berka audit. The
experiment validates parity against every eligible real 3M Phase 2A row before
it performs augmentation or fitting.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase2.windowing import complete_calendar_window

FEATURE_SCHEMA_VERSION = "phase2a-berka-candidate-features-v1"
FEATURES = [
    "avg_monthly_credit", "avg_monthly_debit", "credit_debit_ratio",
    "avg_monthly_net_cashflow", "cashflow_std", "cashflow_cv",
    "positive_cashflow_month_ratio", "negative_cashflow_month_ratio",
    "negative_cashflow_month_count", "inflow_trend", "outflow_trend",
    "avg_balance", "min_balance", "max_balance", "balance_std", "balance_cv",
    "low_balance_frequency", "negative_balance_frequency",
    "end_of_month_balance_trend", "transaction_count", "median_count_months",
]


def canonical_window(loan_date, months=3, account_open_date=None,
                    source_coverage_start=None, source_coverage_end_exclusive=None):
    return complete_calendar_window(
        loan_date, months, account_open_date=account_open_date,
        source_coverage_start=source_coverage_start,
        source_coverage_end_exclusive=source_coverage_end_exclusive,
    )


def extract_behavioral_features(transactions: pd.DataFrame, loan_date,
                                window_start, window_end_exclusive,
                                months=3) -> dict:
    """Compute fixed-window features from typed transactions and post-txn balances.

    Required columns: date, amount, type, balance. `type` has Berka's native
    transaction direction; no labels or loan fields enter this function.
    """
    required = {"date", "amount", "type", "balance"}
    missing = required - set(transactions.columns)
    if missing:
        raise ValueError(f"Missing normalized transaction fields: {sorted(missing)}")
    frame = transactions.copy()
    frame["date"] = pd.to_datetime(frame.date, errors="coerce")
    frame["amount"] = pd.to_numeric(frame.amount, errors="coerce")
    frame["balance"] = pd.to_numeric(frame.balance, errors="coerce")
    loan = pd.Timestamp(loan_date)
    start, end = pd.Timestamp(window_start), pd.Timestamp(window_end_exclusive)
    if start >= end or (end - start).days < 75:
        raise ValueError("Invalid complete-calendar observation interval")
    if frame.date.isna().any() or frame.amount.isna().any():
        raise ValueError("Transaction dates and amounts must be finite and present")
    if (~np.isfinite(frame.amount)).any() or (frame.amount < 0).any():
        raise ValueError("Transaction amounts must be finite nonnegative magnitudes")
    if ((frame.date < start) | (frame.date >= end) | (frame.date >= loan)).any():
        raise ValueError("Transaction outside complete pre-origination window")
    # Keep the caller's already-canonical transaction sequence. Phase 2A sorts
    # each account by parsed date before monthly `last` balance aggregation.
    typ = frame.type.astype(str).str.upper()
    frame["credit"] = np.where(typ == "PRIJEM", frame.amount, 0.0)
    frame["debit"] = np.where(typ.isin(["VYDAJ", "VYBER KARTOU"]), frame.amount, 0.0)
    frame["net"] = frame.credit - frame.debit
    frame["is_credit"] = (typ == "PRIJEM").astype(int)
    frame["is_debit"] = typ.isin(["VYDAJ", "VYBER KARTOU"]).astype(int)
    frame["month"] = frame.date.dt.to_period("M")
    first = start.to_period("M")
    month_index = pd.period_range(first, periods=months, freq="M")
    m = frame.groupby("month").agg(
        credits=("credit", "sum"), debits=("debit", "sum"), net=("net", "sum"),
        txn=("amount", "size"), credit_count=("is_credit", "sum"),
        debit_count=("is_debit", "sum"), bal_min=("balance", "min"),
        bal_max=("balance", "max"), bal_mean=("balance", "mean"),
        bal_end=("balance", "last"),
    ).reindex(month_index)
    for c in ["credits", "debits", "net", "txn", "credit_count", "debit_count"]:
        m[c] = m[c].fillna(0.0)
    net = m.net.astype(float); cr = m.credits.astype(float); db = m.debits.astype(float)
    balances = frame.balance.dropna()
    std_net = float(net.std(ddof=1)) if len(net) > 1 else np.nan
    mean_net = float(net.mean()) if len(net) else np.nan
    bal_std = float(balances.std(ddof=1))
    bal_mean = float(balances.mean())
    represented_ends = m.bal_end.dropna()
    values = {
        "avg_monthly_credit": float(cr.sum()/months),
        "avg_monthly_debit": float(db.sum()/months),
        "credit_debit_ratio": float(cr.sum()/db.sum()) if db.sum() > 0 else np.nan,
        "avg_monthly_net_cashflow": float(net.sum()/months),
        "cashflow_std": std_net,
        "cashflow_cv": std_net/abs(mean_net) if np.isfinite(std_net) and mean_net != 0 else np.nan,
        "positive_cashflow_month_ratio": float((net > 0).sum()/months),
        "negative_cashflow_month_ratio": float((net < 0).sum()/months),
        "negative_cashflow_month_count": int((net < 0).sum()),
        "inflow_trend": float(np.polyfit(np.arange(len(cr)), cr, 1)[0]) if len(cr)>1 else np.nan,
        "outflow_trend": float(np.polyfit(np.arange(len(db)), db, 1)[0]) if len(db)>1 else np.nan,
        "avg_balance": bal_mean,
        "min_balance": float(balances.min()),
        "max_balance": float(balances.max()),
        "balance_std": bal_std,
        "balance_cv": bal_std/abs(bal_mean) if len(balances)>1 and bal_mean != 0 else np.nan,
        "low_balance_frequency": float((balances <= 0).mean()),
        "negative_balance_frequency": float((balances < 0).mean()),
        "end_of_month_balance_trend": float(np.polyfit(np.arange(len(represented_ends)), represented_ends, 1)[0]) if len(represented_ends)>1 else np.nan,
        "transaction_count": int(len(frame)),
        "median_count_months": float(m.txn.median()),
    }
    if set(values) != set(FEATURES):
        raise RuntimeError("Feature schema differs from frozen Phase 2B candidate pool")
    if any(np.isinf(v) for v in values.values() if pd.notna(v)):
        raise ValueError("Non-finite feature generated")
    return values


def assert_feature_parity(real_features: pd.DataFrame, reference_features: pd.DataFrame,
                          atol=1e-7, rtol=1e-8) -> None:
    """Fail if the transaction extractor diverges from corrected Phase 2A rows."""
    ref = reference_features.set_index("loan_id")
    for row in real_features.itertuples(index=False):
        expected = ref.loc[int(row.loan_id)]
        for feature in FEATURES:
            a, b = row._asdict()[feature], expected[feature]
            if pd.isna(a) and pd.isna(b):
                continue
            if pd.isna(a) or pd.isna(b) or not np.isclose(float(a), float(b), atol=atol, rtol=rtol):
                raise RuntimeError(f"Canonical feature parity failed for loan {row.loan_id}/{feature}: {a} != {b}")
