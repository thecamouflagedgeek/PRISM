"""Guardrail response and privacy-safe metadata audit for portfolio sentiment."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


REQUIRED_TEXT_COLUMN = "loan_description"
REQUIRED_LABEL_COLUMN = "label"
ALLOWED_LABELS = {"negative", "neutral", "positive"}


def audit_sentiment_dataset(path: str | Path, provenance: dict | None = None) -> dict:
    """Audit schema/coverage only; never returns text examples or trains a model."""
    source = Path(path)
    if not source.is_file():
        return {"status": "DATASET_NOT_FOUND", "row_count": 0, "label_counts": {}, "text_coverage": 0,
                "evaluation": None, "reason": "The configured dataset is unavailable."}
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        rows = list(reader)
    if REQUIRED_TEXT_COLUMN not in columns or REQUIRED_LABEL_COLUMN not in columns:
        return {"status": "INVALID_SCHEMA", "row_count": len(rows), "label_counts": {}, "text_coverage": 0,
                "evaluation": None, "reason": "Required text and sentiment-label columns are absent."}
    labels = Counter((row.get(REQUIRED_LABEL_COLUMN) or "").strip().lower() for row in rows)
    populated = sum(bool((row.get(REQUIRED_TEXT_COLUMN) or "").strip()) for row in rows)
    provenance_fields = {"source", "license", "collection_method", "label_definition", "permitted_use"}
    provenance_complete = provenance is not None and provenance_fields.issubset(provenance) and all(
        isinstance(provenance[key], str) and provenance[key].strip() for key in provenance_fields)
    label_schema_valid = bool(labels) and set(labels).issubset(ALLOWED_LABELS)
    if not label_schema_valid:
        status, reason = "INVALID_LABELS", "Labels are not explicit sentiment classes."
    elif not provenance_complete:
        status, reason = "UNAVAILABLE", "Dataset provenance, license, collection method, label definition, and permitted use are not documented."
    else:
        status, reason = "AUDIT_READY_NOT_VALIDATED", "Schema metadata is complete; a leakage-controlled evaluation and independent review are still required."
    return {"status": status, "row_count": len(rows), "label_counts": dict(sorted(labels.items())),
            "text_coverage": round(populated / len(rows), 4) if rows else 0,
            "evaluation": None, "provenance_complete": provenance_complete,
            "label_schema_valid": label_schema_valid, "reason": reason}


def portfolio_sentiment_status() -> dict:
    return {
        "status": "UNAVAILABLE",
        "sentiment_classification": None,
        "portfolio_aggregate": None,
        "model_version": None,
        "evaluation": None,
        "decision_use": "NOT_FOR_CREDIT_DECISION",
        "reason": "No approved, provenance-documented sentiment corpus and leakage-controlled evaluation are configured.",
        "limitations": [
            "The repository experiment has no documented source, license, label definition, collection method, or permitted-use statement.",
            "Its TF-IDF vocabulary is fit before the train/test split, and a hand-written behavior rule is combined with text predictions.",
            "Sentiment classification would describe text tone only; it is not a repayment or default-risk estimate.",
        ],
        "required_before_enablement": [
            "Approved and provenance-documented sentiment-labeled text with permitted processing scope.",
            "Leakage-controlled train/validation/test methodology and independent generalization review.",
            "Versioned model, reproducible evaluation artifact, and documented portfolio aggregation semantics.",
        ],
    }
