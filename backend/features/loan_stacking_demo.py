"""Deterministic obligation evidence for a synthetic-only demonstration.

Masked references and recurring debits identify candidate payment streams,
not verified lender accounts or confirmed loan stacking.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
import re
from typing import Any, Mapping, Sequence


_REFERENCE = re.compile(r"^SYN-(?:LENDER|MANDATE)-[A-Z0-9]+$")
_TRANSFER = re.compile(r"\b(?:transfer|own account|between accounts|self transfer)\b", re.I)
_CARD = re.compile(r"\b(?:credit card|card payment|card bill|card repayment)\b", re.I)
_REVERSAL = re.compile(r"\b(?:reversal|reversed|refund)\b", re.I)
_DEBT = re.compile(r"\b(?:loan|emi|instal+ment|repayment|finance)\b", re.I)


def _month(value: str) -> str | None:
    try:
        return date.fromisoformat(value).strftime("%Y-%m")
    except (TypeError, ValueError):
        return None


def _fingerprint(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("date"), row.get("direction"), float(row.get("amount", 0)),
        str(row.get("reference") or "").upper(),
        re.sub(r"\s+", " ", str(row.get("narration") or "").strip().casefold()),
    )


def analyze_synthetic_obligations(
    transactions: Sequence[Mapping[str, Any]],
    *,
    monthly_net_income: float | None,
) -> dict[str, Any]:
    """Summarize repeated referenced debits and period overlap.

    A repayment stream requires a stable fictional masked reference and debits
    in at least two distinct calendar months. No score or policy threshold is
    applied. ``monthly_net_income`` is treated as supplied evidence, not inferred.
    """
    valid = []
    seen_ids: set[str] = set()
    seen_fingerprints: set[tuple[Any, ...]] = set()
    reversed_ids = {
        str(row.get("reversal_of")) for row in transactions
        if isinstance(row, Mapping) and row.get("reversal_of")
    }
    counts = {"duplicate_rows": 0, "reversals": 0, "transfers": 0,
              "credit_card_payments": 0, "unlinked_debt_keywords": 0,
              "referenced_non_debt_debits": 0}

    for row in transactions:
        if not isinstance(row, Mapping):
            continue
        transaction_id = str(row.get("transaction_id") or "")
        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError):
            continue
        month = _month(str(row.get("date") or ""))
        direction = str(row.get("direction") or "").upper()
        narration = str(row.get("narration") or "")
        if not math.isfinite(amount) or amount <= 0 or not month or direction not in {"DR", "CR"}:
            continue
        if (transaction_id and transaction_id in seen_ids) or _fingerprint(row) in seen_fingerprints:
            counts["duplicate_rows"] += 1
            continue
        if transaction_id:
            seen_ids.add(transaction_id)
        seen_fingerprints.add(_fingerprint(row))
        if transaction_id in reversed_ids or _REVERSAL.search(narration):
            counts["reversals"] += 1
            continue
        if _TRANSFER.search(narration):
            counts["transfers"] += 1
            continue
        if _CARD.search(narration):
            counts["credit_card_payments"] += 1
            continue
        valid.append({"transaction_id": transaction_id, "date": str(row["date"]),
                      "month": month, "direction": direction, "amount": amount,
                      "reference": str(row.get("reference") or ""), "narration": narration})

    by_reference: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in valid:
        if row["direction"] != "DR":
            continue
        if _REFERENCE.fullmatch(row["reference"]) and _DEBT.search(row["narration"]):
            by_reference[row["reference"]].append(row)
        elif _DEBT.search(row["narration"]):
            counts["unlinked_debt_keywords"] += 1
        elif _REFERENCE.fullmatch(row["reference"]):
            counts["referenced_non_debt_debits"] += 1

    obligations = []
    for reference, rows in sorted(by_reference.items()):
        months = sorted({row["month"] for row in rows})
        if len(months) < 2:
            continue
        amounts_by_month: dict[str, float] = defaultdict(float)
        for row in rows:
            amounts_by_month[row["month"]] += row["amount"]
        obligations.append({
            "candidate_reference": reference,
            "classification": "CANDIDATE_RECURRING_OBLIGATION",
            "months_observed": months,
            "monthly_amounts": {month: round(amounts_by_month[month], 2) for month in months},
            "transaction_count": len(rows),
            "evidence_transaction_ids": [row["transaction_id"] for row in rows if row["transaction_id"]],
            "grouping_reason": "Same fictional masked reference appears on debit transactions in at least two distinct months.",
            "uncertainty": "A referenced payment stream does not independently verify that this is a loan account.",
        })

    ref_months = {item["candidate_reference"]: set(item["months_observed"]) for item in obligations}
    month_refs: dict[str, list[str]] = defaultdict(list)
    month_amounts: dict[str, float] = defaultdict(float)
    for item in obligations:
        for month, amount in item["monthly_amounts"].items():
            month_refs[month].append(item["candidate_reference"])
            month_amounts[month] += amount
    overlap = {month: sorted(refs) for month, refs in sorted(month_refs.items()) if len(refs) >= 2}
    has_overlap = bool(overlap)
    if has_overlap:
        status = "POSSIBLE_OVERLAPPING_OBLIGATIONS"
        signal = "Observed repayment streams overlap; possible loan stacking requires review."
    elif obligations:
        status = "SINGLE_RECURRING_OBLIGATION"
        signal = "One recurring payment stream was observed; this is not evidence of stacking."
    else:
        status = "INSUFFICIENT_EVIDENCE"
        signal = "Distinct recurring obligations could not be established from the supplied evidence."

    burden = None
    try:
        income = float(monthly_net_income) if monthly_net_income is not None else None
    except (TypeError, ValueError):
        income = None
    if income is not None and income > 0 and obligations:
        observed_months = sorted(month_amounts)
        selected_months = sorted(overlap) if overlap else observed_months
        monthly_obligations = [month_amounts[month] for month in selected_months]
        average = sum(monthly_obligations) / len(monthly_obligations)
        burden = {
            "status": "DESCRIPTIVE_ONLY",
            "monthly_income": round(income, 2),
            "monthly_obligations": round(average, 2),
            "obligation_to_income_ratio": round(average / income, 4),
            "months_used": selected_months,
            "interpretation": "Observed payment burden only; no credit-score penalty or policy threshold is applied.",
        }

    return {
        "synthetic_demo": True,
        "status": status,
        "observed_signal": signal,
        "confirmed_loan_stacking": False,
        "candidate_obligations": obligations,
        "overlapping_months": overlap,
        "overlap_monthly_obligations": {month: round(month_amounts[month], 2) for month in overlap},
        "repayment_burden": burden,
        "excluded_or_uncertain_evidence": counts,
        "limitations": [
            "All records and references are fictional and used only in this demo.",
            "A masked reference and repeated debits identify a candidate payment stream, not a verified loan.",
            "Transfers, reversals, and credit-card payments are excluded from candidate loan streams.",
        ],
    }


def _tx(tx_id: str, day: str, amount: float, ref: str, narration: str = "LOAN EMI AUTOPAY") -> dict[str, Any]:
    return {"transaction_id": tx_id, "date": day, "direction": "DR", "amount": amount,
            "reference": ref, "narration": narration}


SCENARIOS: dict[str, dict[str, Any]] = {
    "overlapping-obligations": {
        "label": "Two recurring payment streams overlap",
        "monthly_net_income": 70000,
        "income_evidence": "Synthetic monthly net income record",
        "transactions": [
            _tx("SYN-TX-101", "2026-07-05", 9800, "SYN-LENDER-A1"),
            _tx("SYN-TX-102", "2026-08-05", 9800, "SYN-LENDER-A1"),
            _tx("SYN-TX-103", "2026-09-05", 9800, "SYN-LENDER-A1"),
            _tx("SYN-TX-201", "2026-07-12", 12400, "SYN-MANDATE-B2"),
            _tx("SYN-TX-202", "2026-08-12", 12400, "SYN-MANDATE-B2"),
            _tx("SYN-TX-203", "2026-09-12", 12400, "SYN-MANDATE-B2"),
        ],
    },
    "single-loan-repayments": {
        "label": "One loan with repeated instalments",
        "monthly_net_income": 70000,
        "income_evidence": "Synthetic monthly net income record",
        "transactions": [_tx(f"SYN-TX-{i}", f"2026-0{month}-08", 9800, "SYN-LENDER-A1")
                         for i, month in enumerate((7, 8, 9), start=301)],
    },
    "duplicates-transfers": {
        "label": "Duplicate, reversal, transfer, and card-payment controls",
        "monthly_net_income": 70000,
        "income_evidence": "Synthetic monthly net income record",
        "transactions": [
            _tx("SYN-TX-401", "2026-07-05", 9800, "SYN-LENDER-A1"),
            _tx("SYN-TX-401", "2026-07-05", 9800, "SYN-LENDER-A1"),
            _tx("SYN-TX-402", "2026-08-05", 9800, "SYN-LENDER-A1"),
            _tx("SYN-TX-403", "2026-09-05", 9800, "SYN-LENDER-A1"),
            _tx("SYN-TX-404", "2026-08-07", 15000, "SYN-MANDATE-XFER", "INTERNAL TRANSFER LOAN"),
            _tx("SYN-TX-405", "2026-08-09", 5000, "SYN-MANDATE-CARD", "CREDIT CARD BILL PAYMENT"),
            {"transaction_id": "SYN-TX-406", "date": "2026-08-10", "direction": "CR", "amount": 9800,
             "reference": "SYN-LENDER-A1", "narration": "LOAN EMI REVERSAL", "reversal_of": "SYN-TX-402"},
        ],
    },
    "insufficient-evidence": {
        "label": "Loan keywords without distinct references",
        "monthly_net_income": None,
        "income_evidence": None,
        "transactions": [_tx("SYN-TX-501", "2026-08-05", 9800, "", "LOAN EMI"),
                         _tx("SYN-TX-502", "2026-09-05", 12400, "", "LOAN REPAYMENT")],
    },
}


def scenario_result(scenario_id: str) -> dict[str, Any] | None:
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        return None
    transactions = [dict(row) for row in scenario["transactions"]]
    result = analyze_synthetic_obligations(transactions, monthly_net_income=scenario["monthly_net_income"])
    return {"scenario_id": scenario_id, "label": scenario["label"],
            "income_evidence": scenario["income_evidence"], "transactions": transactions, **result}
