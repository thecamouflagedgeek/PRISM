"""Conservative, explainable review of recurring loan-like bank debits.

This extracts candidate payment streams. It is not a loan-account verifier and
never produces a calibrated probability, credit score, or lending decision.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import math
import re
from typing import Any, Iterable, Mapping

import pandas as pd


RULE_VERSION = "OBSERVED_REPAYMENT_STREAM_REVIEW_V1"
_LOAN = re.compile(r"\b(?:loan|emi|instal+ment|installment|repayment|repay|nach\s+loan|ecs\s+loan)\b", re.I)
_CARD = re.compile(r"\b(?:credit\s*card|card\s*(?:bill|payment|repayment)|cc\s*(?:bill|payment|repayment))\b", re.I)
_TRANSFER = re.compile(r"\b(?:own\s+account|self\s+transfer|internal\s+transfer|between\s+own\s+accounts)\b", re.I)
_REVERSAL = re.compile(r"\b(?:refund|reversal|reversed|chargeback|cancelled|canceled)\b", re.I)
_REFERENCE = re.compile(
    r"\b(?:loan|mandate)\s*(?:account|ref(?:erence)?|id)\s*[:#=/ -]*\s*([A-Z0-9][A-Z0-9-]{3,})\b", re.I
)
_STOP = {
    "loan", "emi", "instalment", "installment", "repayment", "repay", "nach", "ecs",
    "auto", "debit", "payment", "monthly", "standing", "instruction", "mandate",
    "account", "ref", "reference", "id", "bank", "transfer", "to", "by", "for",
    "refund", "reversal", "reversed", "chargeback", "cancelled", "canceled",
}


def _month(value: Any) -> str | None:
    parsed = _parsed_date(value)
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m")


def _parsed_date(value: Any):
    raw = str(value).strip()
    return (pd.to_datetime(raw, errors="coerce", format="ISO8601")
            if re.match(r"^\d{4}-\d{2}-\d{2}(?:$|T)", raw)
            else pd.to_datetime(raw, errors="coerce", dayfirst=True))


def _source_id(row: Mapping[str, Any], index: int) -> str:
    document = row.get("source_document_id")
    page = row.get("source_page")
    line = row.get("source_line")
    if document is not None and page is not None and pd.notna(page):
        return f"doc:{document}/page:{int(page)}/line:{int(line) if line is not None and pd.notna(line) else 'unknown'}"
    return f"transaction-row:{index + 1}"


def _signature(narration: str) -> tuple[str | None, str | None, str]:
    explicit = _REFERENCE.search(narration)
    if explicit:
        raw_ref = re.sub(r"[^A-Z0-9-]", "", explicit.group(1).upper())
        digest = hashlib.sha256(raw_ref.encode()).hexdigest()[:10]
        return f"reference:{digest}", "EXPLICIT_LOAN_OR_MANDATE_REFERENCE", f"…{raw_ref[-2:]}"
    text = narration.upper()
    text = re.sub(r"\b(?:UTR|RRN|TXN|TRANSACTION)\s*[:#/-]?\s*[A-Z0-9-]+\b", " ", text)
    text = re.sub(r"\b\d{4,}\b", " ", text)
    tokens = [token.lower() for token in re.findall(r"[A-Z][A-Z0-9&'-]{1,}", text)
              if token.lower() not in _STOP]
    if not tokens:
        return None, None, ""
    descriptor = " ".join(tokens)
    digest = hashlib.sha256(descriptor.encode()).hexdigest()[:10]
    return f"narration:{digest}", "NORMALIZED_NARRATION_ONLY", ""


def review_loan_obligations(
    transactions: Iterable[Mapping[str, Any]] | pd.DataFrame | None,
    *,
    observed_months: Iterable[str] | None = None,
    extraction_quality: float | None = None,
) -> dict[str, Any]:
    """Return traceable candidate evidence with explicit uncertainty.

    A candidate stream requires loan-like narration on debits in at least two
    distinct months and a stable explicit reference or normalized description.
    Separate streams are only an observed overlap signal; never confirmed loans.
    """
    if isinstance(transactions, pd.DataFrame):
        rows = transactions.to_dict(orient="records")
    else:
        rows = list(transactions or [])
    seen: set[tuple[Any, ...]] = set()
    unique: list[tuple[int, dict[str, Any], str]] = []
    exclusions = {"duplicate_rows": 0, "reversals_or_refunds": 0, "internal_transfers": 0,
                  "credit_card_payments": 0, "non_debit_rows": 0, "non_loan_debits": 0,
                  "unlinked_loan_like_debits": 0}
    excluded_ids: dict[str, list[str]] = defaultdict(list)
    for index, source in enumerate(rows):
        row = dict(source)
        narration = str(row.get("narration") or "").strip()
        direction = str(row.get("type", row.get("direction", ""))).strip().upper()
        parsed_date = _month(row.get("date"))
        try:
            amount = abs(float(row.get("amount")))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(amount) or amount <= 0 or parsed_date is None:
            continue
        normalized = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", narration.upper())).strip()
        balance = row.get("closing_balance")
        full_date = str(row.get("date"))[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", str(row.get("date", ""))) else parsed_date
        fingerprint = (full_date, round(amount, 2), direction, normalized,
                       None if balance is None or pd.isna(balance) else str(balance))
        if fingerprint in seen:
            exclusions["duplicate_rows"] += 1
            excluded_ids["duplicate_rows"].append(_source_id(row, index))
            continue
        seen.add(fingerprint)
        row.update({"_month": parsed_date, "_day": int(_parsed_date(row.get("date")).day),
                    "_amount": amount, "_direction": direction,
                    "_narration": narration, "_source_id": _source_id(row, index)})
        unique.append((index, row, narration))

    # Reversal rows are evidence to exclude. Where a reversal repeats the same
    # obligation reference/signature and amount within the same month, exclude
    # the paired debit as well rather than double-counting the cancelled item.
    reversal_keys = set()
    for _, row, narration in unique:
        if _REVERSAL.search(narration):
            key, _, _ = _signature(narration)
            reversal_keys.add((row.get("reversal_of"), key, row["_month"], round(row["_amount"], 2)))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    raw_candidates: list[dict[str, Any]] = []
    for index, row, narration in unique:
        direction = row["_direction"]
        if _REVERSAL.search(narration):
            exclusions["reversals_or_refunds"] += 1
            excluded_ids["reversals_or_refunds"].append(row["_source_id"])
            continue
        if _TRANSFER.search(narration):
            exclusions["internal_transfers"] += 1
            excluded_ids["internal_transfers"].append(row["_source_id"])
            continue
        if _CARD.search(narration):
            exclusions["credit_card_payments"] += 1
            excluded_ids["credit_card_payments"].append(row["_source_id"])
            continue
        if direction != "DR":
            exclusions["non_debit_rows"] += 1
            excluded_ids["non_debit_rows"].append(row["_source_id"])
            continue
        if not _LOAN.search(narration):
            exclusions["non_loan_debits"] += 1
            excluded_ids["non_loan_debits"].append(row["_source_id"])
            continue
        key, reference_type, masked_reference = _signature(narration)
        if key is None:
            exclusions["unlinked_loan_like_debits"] += 1
            raw_candidates.append({"source_transaction_id": row["_source_id"], "month": row["_month"],
                                   "amount": round(row["_amount"], 2), "review_reason": "NO_STABLE_CREDITOR_OR_REFERENCE"})
            continue
        explicit = row.get("reversal_of")
        if (explicit, key, row["_month"], round(row["_amount"], 2)) in reversal_keys:
            exclusions["reversals_or_refunds"] += 1
            excluded_ids["reversals_or_refunds"].append(row["_source_id"])
            continue
        grouped[key].append({"source_transaction_id": row["_source_id"], "month": row["_month"],
                             "day": row["_day"],
                             "amount": row["_amount"], "reference_type": reference_type,
                             "masked_reference": masked_reference})
        raw_candidates.append({"source_transaction_id": row["_source_id"], "month": row["_month"],
                               "amount": round(row["_amount"], 2), "review_reason": "LOAN_LIKE_DEBIT"})

    candidates = []
    for key, evidence in sorted(grouped.items()):
        month_totals: dict[str, float] = defaultdict(float)
        month_counts: dict[str, int] = defaultdict(int)
        month_days: dict[str, list[int]] = defaultdict(list)
        for item in evidence:
            month_totals[item["month"]] += item["amount"]
            month_counts[item["month"]] += 1
            month_days[item["month"]].append(item["day"])
        months = sorted(month_totals)
        if len(months) < 2:
            continue
        amounts = list(month_totals.values())
        mean = sum(amounts) / len(amounts)
        cv = math.sqrt(sum((value - mean) ** 2 for value in amounts) / len(amounts)) / mean if mean else None
        all_days = [day for days in month_days.values() for day in days]
        day_span = max(all_days) - min(all_days)
        between = pd.period_range(months[0], months[-1], freq="M").astype(str).tolist()
        reference_type = evidence[0]["reference_type"]
        candidates.append({
            "candidate_id": key.split(":", 1)[1],
            "classification": "CANDIDATE_RECURRING_PAYMENT_STREAM",
            "reference_type": reference_type,
            "masked_reference": evidence[0]["masked_reference"] or None,
            "months_observed": months,
            "missing_months": [month for month in between if month not in month_totals],
            "monthly_amounts": {month: round(month_totals[month], 2) for month in months},
            "payment_days_of_month": {month: sorted(month_days[month]) for month in months},
            "day_of_month_span": day_span,
            "timing_pattern": "REGULAR_DAY_OF_MONTH_WITHIN_5_DAYS" if day_span <= 5 else "IRREGULAR_OR_UNCERTAIN",
            "amount_coefficient_of_variation": round(cv, 4) if cv is not None else None,
            "monthly_amount_stable_under_20pct_rule": cv is not None and cv <= 0.20,
            "multiple_matching_debits_in_month": [month for month, count in month_counts.items() if count > 1],
            "source_transaction_ids": [item["source_transaction_id"] for item in evidence],
            "uncertainty": "Narration/reference recurrence is an observed payment stream, not a verified loan account or borrower obligation.",
        })

    expected = sorted(set(str(month) for month in (observed_months or [])))
    actual = sorted({row["_month"] for _, row, _ in unique})
    coverage_months = expected or actual
    missing_coverage = []
    if expected:
        missing_coverage = [month for month in expected if month not in set(actual)]
    elif coverage_months:
        span = pd.period_range(coverage_months[0], coverage_months[-1], freq="M").astype(str).tolist()
        missing_coverage = [month for month in span if month not in set(coverage_months)]
    overlaps: dict[str, list[str]] = defaultdict(list)
    for item in candidates:
        for month in item["months_observed"]:
            overlaps[month].append(item["candidate_id"])
    overlaps = {month: sorted(ids) for month, ids in sorted(overlaps.items()) if len(set(ids)) >= 2}
    sufficiency_gaps = []
    if extraction_quality is None or extraction_quality < 0.80:
        sufficiency_gaps.append("EXTRACTION_QUALITY_BELOW_80_PERCENT_OR_UNKNOWN")
    if len(coverage_months) < 2:
        sufficiency_gaps.append("FEWER_THAN_2_OBSERVED_MONTHS")
    if missing_coverage:
        sufficiency_gaps.append("GAPS_IN_OBSERVED_MONTH_COVERAGE")
    if sufficiency_gaps:
        status = "INSUFFICIENT_EVIDENCE"
        signal = ("Candidate payment streams are present, but coverage or extraction quality is insufficient for an overlap signal: "
                  + ", ".join(sufficiency_gaps) + ".")
    elif overlaps:
        status = "POSSIBLE_OVERLAPPING_REPAYMENT_STREAMS"
        signal = "Separate recurring loan-like payment descriptions overlap; human review is required. This is not confirmed loan stacking."
    elif candidates:
        status = "SINGLE_RECURRING_PAYMENT_STREAM_OBSERVED"
        signal = "One recurring loan-like payment stream was observed; this does not establish all debts or prove stacking."
    else:
        status = "INSUFFICIENT_EVIDENCE"
        signal = "Available transactions do not establish distinct recurring repayment streams. This is not evidence that no other obligations exist."
    return {
        "status": status,
        "observed_signal": signal,
        "confirmed_loan_stacking": False,
        "rule_version": RULE_VERSION,
        "decision_use": "MANUAL_REVIEW_ONLY_NOT_A_SCORE_OR_LENDING_DECISION",
        "calibrated_confidence": None,
        "raw_candidate_transactions": raw_candidates,
        "candidate_payment_streams": candidates,
        "inferred_obligations": [],
        "overlapping_months": overlaps,
        "data_coverage": {"transaction_months": coverage_months, "missing_months": missing_coverage,
                          "extraction_quality_min": extraction_quality,
                          "transactions_reviewed": len(unique), "sufficiency_gaps": sufficiency_gaps},
        "exclusions": exclusions,
        "excluded_transaction_ids": dict(excluded_ids),
        "limitations": [
            "Bank narration and recurring amounts cannot verify a lender, loan account, contractual instalment, or current balance.",
            "A shared creditor description may combine separate loans; varying descriptions may split one loan.",
            "No calibrated classifier or confidence estimate is available; ambiguous evidence requires human review.",
            "Transfers, refunds/reversals, and credit-card bill payments are excluded from candidate streams.",
        ],
    }
