"""
PRISM - Assessment Service

Orchestrates the independent PRISM risk engines:

    1. Credit Risk
    2. Fraud Risk
    3. Document / Cross-Document Consistency Risk

Important:
- Existing credit-scoring behaviour is preserved.
- Existing fraud-scoring behaviour is preserved.
- Document risk is an independent assessment signal.
- Document risk does NOT modify credit score or PD.
- Raw document data is kept separate from engineered scoring features.
"""

from typing import Any, Dict, List, Optional

from scoring.risk_scorer import score_borrower
from fraud.integration import assess_fraud

from document_validation.consistency_engine import assess_consistency
from document_validation.consistency_adapter import (
    build_consistency_inputs,
)


def assess_borrower(
    bank: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
    application: Optional[Dict[str, Any]] = None,
    application_history: Optional[List[Dict[str, Any]]] = None,
    transactions: Optional[Any] = None,
    bank_document: Any = None,
    salary_document: Optional[Dict[str, Any]] = None,
    utility_document: Any = None,
) -> Dict[str, Any]:
    """
    Run the complete PRISM borrower assessment.

    Assessment layers:

        Credit Risk
            Existing WoE + Logistic Regression scorecard.

        Fraud Risk
            Existing rule-based fraud engine.

        Document Risk
            Cross-document consistency checks using raw structured
            document data.

    Parameters
    ----------
    bank:
        Engineered bank features used by the credit scorecard.

    salary:
        Engineered salary features used by the credit scorecard.

    utility:
        Engineered utility features used by the credit scorecard.

    application:
        Borrower/application data, when available.

    application_history:
        Previous applications for the borrower.

    transactions:
        Canonical bank transaction data used by the fraud engine.

    bank_document:
        Raw structured bank document data used by document
        consistency checks. For the current pipeline this is
        the canonical bank transaction DataFrame.

    salary_document:
        Raw structured salary parser output used by document
        consistency checks.

    utility_document:
        Raw structured utility DataFrame used by document
        consistency checks.

    Returns
    -------
    dict
        Combined PRISM assessment containing:

            - existing credit-risk fields at top level
            - credit_risk
            - fraud_risk
            - document_risk
    """

    # ---------------------------------------------------------
    # Normalize optional inputs
    # ---------------------------------------------------------

    bank = bank or {}
    salary = salary or {}
    utility = utility or {}
    application = application or {}
    application_history = application_history or []
    transactions = transactions if transactions is not None else []

    # ---------------------------------------------------------
    # 1. CREDIT RISK
    #
    # Existing scoring pipeline.
    # DO NOT modify its internal behaviour here.
    #
    # The scorecard receives engineered feature dictionaries.
    # ---------------------------------------------------------

    credit_risk = score_borrower(
        bank=bank,
        salary=salary,
        utility=utility,
    )

    # ---------------------------------------------------------
    # 2. FRAUD RISK
    #
    # Existing fraud engine.
    #
    # The fraud engine receives canonical bank transactions
    # independently of the credit feature dictionaries.
    # ---------------------------------------------------------

    fraud_risk = assess_fraud(
        borrower=application,
        application_history=application_history,
        transactions=transactions,
    )

    # ---------------------------------------------------------
    # 3. DOCUMENT / CROSS-DOCUMENT CONSISTENCY
    #
    # Document intelligence operates on raw structured
    # document data rather than scorecard features.
    #
    # This keeps document risk independent from credit scoring.
    # ---------------------------------------------------------

    consistency_inputs = build_consistency_inputs(
        application=application,
        salary=(
            salary_document
            if salary_document is not None
            else salary
        ),
        bank=(
            bank_document
            if bank_document is not None
            else transactions
        ),
        utility=(
            utility_document
            if utility_document is not None
            else utility
        ),
    )

    document_risk = assess_consistency(
        **consistency_inputs,
    )

    # ---------------------------------------------------------
    # 4. COMBINED ASSESSMENT
    #
    # Keep existing credit fields at the top level for
    # backwards compatibility with existing callers.
    #
    # New intelligence layers are also exposed explicitly.
    # ---------------------------------------------------------

    result = dict(credit_risk)

    result.update(
        {
            "credit_risk": credit_risk,
            "fraud_risk": fraud_risk,
            "document_risk": document_risk,
        }
    )

    return result


__all__ = [
    "assess_borrower",
]