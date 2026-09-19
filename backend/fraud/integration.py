"""Boundary adapter between PRISM parser output and the P1 fraud engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .fraud_engine import FraudEngine


_IDENTITY_FIELDS = ("pan", "phone_number", "bank_account", "borrower_id")
_TRANSACTION_FIELDS = (
    "date", "transaction_date", "amount", "credit", "debit", "type",
    "transaction_type", "narration", "balance", "closing_balance",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        return dict(converted) if isinstance(converted, Mapping) else {}
    return {}


def normalize_borrower(borrower: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep only stable identity fields plus assessment timing metadata.

    An application or session id is deliberately never promoted to borrower_id.
    """
    source = _as_mapping(borrower)
    result = {field: source[field] for field in _IDENTITY_FIELDS if source.get(field) not in (None, "")}
    for field in ("application_id", "application_date", "created_at", "status"):
        if source.get(field) not in (None, ""):
            result[field] = source[field]
    return result


def normalize_transactions(transactions: Any) -> list[dict[str, Any]]:
    """Map canonical bank rows to the fields consumed by fraud rules.

    Malformed rows are excluded rather than allowed to affect the credit path.
    """
    if transactions is None:
        return []
    if hasattr(transactions, "to_dict"):
        transactions = transactions.to_dict(orient="records")
    if not isinstance(transactions, Sequence) or isinstance(transactions, (str, bytes)):
        raise TypeError("transactions must be a sequence of mapping records")

    normalized: list[dict[str, Any]] = []
    for transaction in transactions:
        row = _as_mapping(transaction)
        if row:
            normalized.append({key: row[key] for key in _TRANSACTION_FIELDS if key in row})
    return normalized


def assess_fraud(
    borrower: Mapping[str, Any] | None = None,
    application_history: Sequence[Mapping[str, Any]] | None = None,
    transactions: Any = None,
    reference_time: datetime | str | None = None,
) -> dict[str, Any]:
    """Run the existing fraud engine with normalized optional assessment data."""
    history = [] if application_history is None else list(application_history)
    if not all(isinstance(item, Mapping) for item in history):
        raise TypeError("application_history must contain mapping records")
    normalized_borrower = normalize_borrower(borrower)
    current_application_id = normalized_borrower.get("application_id")
    normalized_history = [
        _as_mapping(item)
        for item in history
        if not current_application_id
        or _as_mapping(item).get("application_id") != current_application_id
    ]
    return FraudEngine().assess(
        borrower=normalized_borrower,
        applications=normalized_history,
        transactions=normalize_transactions(transactions),
        reference_time=reference_time,
    )
