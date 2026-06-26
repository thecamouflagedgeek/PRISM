"""
PRISM — Stage 9: Confidence Layer
===================================
Literature basis:
    Khandani et al. (2010) — Consumer Credit Risk Models via Machine-Learning Algorithms
    RBI DPDPA (2023) — Data Protection and Algorithmic Accountability
    Basel II Pillar 1 — Data Quality Standards for IRB Models

What Confidence measures:
    The confidence score quantifies HOW RELIABLE the PD estimate is,
    separate from what the PD value actually is.

    A low-confidence HIGH score is not the same as a high-confidence HIGH score.
    This matters for:
        1. Credit limit decisions (low confidence → lower exposure)
        2. Manual review triggers (low confidence → human underwriter review)
        3. Regulatory reporting (data quality dimensions must be logged)

Four components per PRISM's methodology:

    1. Document Coverage (C_doc):
       Proportion of required document types present.
       Missing bank statement → significant information gap.

    2. Data Quality Score (C_qual):
       Proportion of expected fields successfully extracted and validated.
       Derived from Stage 1 extraction success rates.

    3. Fraud Confidence (C_fraud):
       Output of Stage 10 fraud detection module.
       Low fraud confidence → low overall confidence even if data is complete.

    4. Model Certainty (C_model):
       How far the PD is from 0.5 (the decision boundary).
       A borrower with PD=0.51 is barely classified; PD=0.02 is very certain.
       Certainty = |PD - 0.5| × 2  (maps to [0, 1])

Combined:
    Confidence = C_doc × C_qual × C_fraud × C_model

    Multiplicative structure ensures ANY single zero collapses overall confidence —
    a document with 100% quality but no fraud check still produces zero confidence.
"""

import numpy as np
import pandas as pd
import joblib
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class DocumentCoverage:
    """
    Tracks which document types were successfully parsed.
    Three primary sources: bank, salary, utility.
    """
    has_bank_statement : bool = False
    has_salary_slip    : bool = False
    has_utility_bill   : bool = False

    @property
    def coverage_score(self) -> float:
        """
        Weighted coverage — bank statement is most information-dense.
        Weights per PRISM feature contribution:
            bank    : credit_debit_ratio, cashflow_cv, min_balance → 3/5 features
            salary  : net_to_gross_ratio → 1/5 features
            utility : utility_stability  → 1/5 features
        """
        return (
            0.60 * int(self.has_bank_statement) +
            0.20 * int(self.has_salary_slip)    +
            0.20 * int(self.has_utility_bill)
        )


@dataclass
class DataQuality:
    """
    Per-feature extraction quality flags from Stage 1 parsing.
    Each field is True if the value was successfully extracted AND validated.
    """
    credit_debit_ratio_ok : bool = False
    cashflow_cv_ok        : bool = False
    net_to_gross_ratio_ok : bool = False
    utility_stability_ok  : bool = False
    min_balance_ok        : bool = False

    @property
    def quality_score(self) -> float:
        flags = [
            self.credit_debit_ratio_ok,
            self.cashflow_cv_ok,
            self.net_to_gross_ratio_ok,
            self.utility_stability_ok,
            self.min_balance_ok
        ]
        return sum(flags) / len(flags)


def model_certainty(pd_value: float) -> float:
    """
    How certain the model is about its prediction.
    Maximum certainty at PD=0 or PD=1 (definitive).
    Minimum certainty at PD=0.5 (coin flip — model has no opinion).

    certainty = |PD - 0.5| × 2  ∈ [0, 1]
    """
    return abs(pd_value - 0.5) * 2


def compute_confidence(
    doc_coverage : DocumentCoverage,
    data_quality : DataQuality,
    fraud_confidence : float,   # output of Stage 10, ∈ [0, 1]
    pd_value : float
) -> Dict:
    """
    Compute composite confidence score.

    Parameters
    ----------
    doc_coverage     : DocumentCoverage dataclass
    data_quality     : DataQuality dataclass
    fraud_confidence : float ∈ [0, 1] from fraud detection module
    pd_value         : float, Probability of Default from Stage 6

    Returns
    -------
    dict with component scores and final confidence
    """
    c_doc    = doc_coverage.coverage_score
    c_qual   = data_quality.quality_score
    c_fraud  = float(np.clip(fraud_confidence, 0, 1))
    c_model  = model_certainty(pd_value)

    # Multiplicative combination
    confidence = c_doc * c_qual * c_fraud * c_model

    # Map to [0, 100] percentage
    confidence_pct = round(confidence * 100, 2)

    # Confidence band
    if confidence_pct >= 80:
        band = "High Confidence"
    elif confidence_pct >= 50:
        band = "Moderate Confidence"
    elif confidence_pct >= 20:
        band = "Low Confidence — Manual Review Recommended"
    else:
        band = "Very Low Confidence — Do Not Automate Decision"

    return {
        "confidence_pct"       : confidence_pct,
        "band"                 : band,
        "components": {
            "document_coverage"  : round(c_doc,   4),
            "data_quality"       : round(c_qual,  4),
            "fraud_confidence"   : round(c_fraud, 4),
            "model_certainty"    : round(c_model, 4),
        }
    }


def confidence_for_api_response(
    bank    : Optional[dict],
    salary  : Optional[dict],
    utility : Optional[dict],
    pd_value: float,
    fraud_confidence: float = 1.0
) -> Dict:
    """
    Convenience wrapper for inference-time use in scorer.py / FastAPI endpoint.
    Automatically infers doc coverage and data quality from the parsed dicts.
    """
    # Document coverage
    coverage = DocumentCoverage(
        has_bank_statement = bank    is not None,
        has_salary_slip    = salary  is not None,
        has_utility_bill   = utility is not None
    )

    # Data quality from non-null field values
    def valid(x):
        return x is not None and not (isinstance(x, float) and np.isnan(x))

    quality = DataQuality(
        credit_debit_ratio_ok = valid(bank.get("credit_debit_ratio") if bank else None),
        cashflow_cv_ok        = valid(bank.get("cashflow_cv")        if bank else None),
        net_to_gross_ratio_ok = valid(salary.get("net_to_gross_ratio") if salary else None),
        utility_stability_ok  = valid(utility.get("payment_discipline_flag") if utility else None),
        min_balance_ok        = valid(bank.get("min_balance")        if bank else None)
    )

    return compute_confidence(coverage, quality, fraud_confidence, pd_value)


# ── STANDALONE RUN ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Stage 9 — Confidence Layer Demo\n")

    scenarios = [
        {
            "label": "Full documents, high fraud confidence",
            "bank"   : {"credit_debit_ratio": 1.5, "cashflow_cv": 0.3, "min_balance": 40000},
            "salary" : {"net_to_gross_ratio": 0.82},
            "utility": {"payment_discipline_flag": True},
            "pd"     : 0.08,
            "fraud"  : 0.95
        },
        {
            "label": "Bank only, moderate fraud confidence",
            "bank"   : {"credit_debit_ratio": 0.9, "cashflow_cv": 0.7, "min_balance": 10000},
            "salary" : None,
            "utility": None,
            "pd"     : 0.45,
            "fraud"  : 0.70
        },
        {
            "label": "All documents, borderline PD, low fraud confidence",
            "bank"   : {"credit_debit_ratio": 1.1, "cashflow_cv": 0.5, "min_balance": 20000},
            "salary" : {"net_to_gross_ratio": 0.71},
            "utility": {"payment_discipline_flag": False},
            "pd"     : 0.49,
            "fraud"  : 0.40
        },
    ]

    for s in scenarios:
        result = confidence_for_api_response(
            bank    = s["bank"],
            salary  = s["salary"],
            utility = s["utility"],
            pd_value= s["pd"],
            fraud_confidence = s["fraud"]
        )

        print(f"  Scenario: {s['label']}")
        print(f"    Confidence : {result['confidence_pct']}%  →  {result['band']}")
        for k, v in result["components"].items():
            print(f"    {k:25s}: {v}")
        print()

    print("Stage 9 complete.")