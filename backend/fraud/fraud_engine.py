"""
PRISM P1 — Fraud Engine

Aggregates identity/loan-stacking and transaction anomaly rules
into an explainable heuristic fraud score.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

try:  # Package import used by the backend.
    from .fraud_rules import IDENTITY_RULES, TRANSACTION_RULES
except ImportError:  # Direct ``python test_fraud.py`` compatibility.
    from fraud_rules import IDENTITY_RULES, TRANSACTION_RULES


_IDENTITY_RULE_NAMES = {
    "DUPLICATE_IDENTITY",
    "MULTIPLE_RECENT_APPLICATIONS",
    "ACTIVE_LOAN_OVERLAP",
    "RAPID_REAPPLICATION",
}

_SEVERITY_BY_RULE = {
    "DUPLICATE_IDENTITY": "high",
    "MULTIPLE_RECENT_APPLICATIONS": "medium",
    "ACTIVE_LOAN_OVERLAP": "high",
    "RAPID_REAPPLICATION": "medium",
    "LARGE_DEPOSIT": "medium",
    "SUDDEN_BALANCE_INCREASE": "high",
    "REPEATED_IDENTICAL_TRANSACTIONS": "medium",
    "CREDIT_DEBIT_SPIKE": "medium",
    "MONEY_IN_OUT_PATTERN": "high",
    "ROUND_NUMBER_ACTIVITY": "low",
    "ABNORMAL_BALANCE_BEHAVIOUR": "medium",
}


class FraudEngine:

    ENGINE_VERSION = "P1-v1"

    def __init__(
        self,
        run_identity_rules: bool = True,
        run_transaction_rules: bool = True,
    ):
        self.run_identity_rules = run_identity_rules
        self.run_transaction_rules = run_transaction_rules

    # ========================================================
    # SCORE
    # ========================================================

    @staticmethod
    def _calculate_score(
        flags: Sequence[Mapping[str, Any]]
    ) -> int:

        score = sum(
            int(flag.get("weight", 0))
            for flag in flags
        )

        return min(100, score)

    # ========================================================
    # STATUS
    # ========================================================

    @staticmethod
    def _status(score: int) -> str:

        if score == 0:
            return "CLEAR"

        if score >= 81:
            return "CRITICAL"

        if score >= 61:
            return "HIGH"

        if score >= 31:
            return "MEDIUM"

        return "LOW"

    @staticmethod
    def _present_flag(flag: Mapping[str, Any]) -> dict[str, Any]:
        """Add API presentation fields without changing a rule's evidence."""
        result = dict(flag)
        rule = str(result.get("rule", ""))
        result["category"] = (
            "identity" if rule in _IDENTITY_RULE_NAMES else "transaction"
        )
        result["severity"] = _SEVERITY_BY_RULE.get(rule, "medium")
        return result

    # ========================================================
    # RUN
    # ========================================================

    def assess(
        self,
        borrower: Mapping[str, Any],
        applications: Sequence[Mapping[str, Any]] | None = None,
        transactions: Sequence[Mapping[str, Any]] | None = None,
        reference_time: Any = None,
    ) -> dict[str, Any]:

        applications = applications or []
        transactions = transactions or []

        flags: list[dict[str, Any]] = []

        # ----------------------------------------------------
        # IDENTITY / LOAN STACKING
        # ----------------------------------------------------

        if self.run_identity_rules:

            for rule in IDENTITY_RULES:

                if rule.__name__ in {
                    "multiple_recent_applications",
                    "rapid_reapplication",
                }:

                    result = rule(
                        borrower,
                        applications,
                        reference_time,
                    )

                else:

                    result = rule(
                        borrower,
                        applications,
                    )

                if result:
                    flags.append(self._present_flag(result))

        # ----------------------------------------------------
        # TRANSACTION ANOMALIES
        # ----------------------------------------------------

        if self.run_transaction_rules:

            for rule in TRANSACTION_RULES:

                result = rule(
                    transactions
                )

                if result:
                    flags.append(self._present_flag(result))

        # ----------------------------------------------------
        # AGGREGATION
        # ----------------------------------------------------

        fraud_score = self._calculate_score(
            flags
        )

        fraud_status = self._status(
            fraud_score
        )

        return {
            "fraud_score": fraud_score,
            "fraud_status": fraud_status,
            "flags": flags,
            "rule_count": len(flags),
            "engine_version": self.ENGINE_VERSION,

            # Important semantic distinction:
            "score_semantics":
                "heuristic weighted rule score; "
                "not a calibrated probability",
        }


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def run_fraud_assessment(
    borrower: Mapping[str, Any],
    applications: Sequence[Mapping[str, Any]] | None = None,
    transactions: Sequence[Mapping[str, Any]] | None = None,
    reference_time: Any = None,
) -> dict[str, Any]:

    engine = FraudEngine()

    return engine.assess(
        borrower=borrower,
        applications=applications,
        transactions=transactions,
        reference_time=reference_time,
    )
