"""
PRISM — Cross-Document Consistency Engine

Runs consistency checks across:
    - Loan application
    - Bank statement
    - Salary slip
    - Utility document

This module is separate from:
    - Credit Risk
    - Fraud Risk
    - Document Validation
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .consistency_rules import (
    check_name_consistency,
    check_pan_consistency,
    check_account_consistency,
    check_income_consistency,
    check_employment_consistency,
    check_statement_period,
)


ENGINE_VERSION = "P1-CONSISTENCY-v1"


SEVERITY_WEIGHT = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


class ConsistencyEngine:

    def __init__(self) -> None:
        self.version = ENGINE_VERSION

    def assess(
        self,
        application: Optional[Dict[str, Any]] = None,
        salary: Optional[Dict[str, Any]] = None,
        bank: Optional[Dict[str, Any]] = None,
        utility: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        application = application or {}
        salary = salary or {}
        bank = bank or {}
        utility = utility or {}

        findings = []

        # ----------------------------------------------------
        # IDENTITY CONSISTENCY
        # ----------------------------------------------------

        result = check_name_consistency(
            application,
            salary,
            bank,
            utility,
        )

        if result is not None:
            findings.append(result)

        # ----------------------------------------------------
        # PAN CONSISTENCY
        # ----------------------------------------------------

        result = check_pan_consistency(
            application,
            salary,
            bank,
        )

        if result is not None:
            findings.append(result)

        # ----------------------------------------------------
        # BANK ACCOUNT CONSISTENCY
        # ----------------------------------------------------

        result = check_account_consistency(
            application,
            bank,
        )

        if result is not None:
            findings.append(result)

        # ----------------------------------------------------
        # INCOME CONSISTENCY
        # ----------------------------------------------------

        result = check_income_consistency(
            application,
            salary,
            bank,
        )

        if result is not None:
            findings.append(result)

        # ----------------------------------------------------
        # EMPLOYMENT CONSISTENCY
        # ----------------------------------------------------

        result = check_employment_consistency(
            application,
            salary,
        )

        if result is not None:
            findings.append(result)

        # ----------------------------------------------------
        # STATEMENT PERIOD
        # ----------------------------------------------------

        result = check_statement_period(
            bank,
        )

        if result is not None:
            findings.append(result)

        # ----------------------------------------------------
        # SEVERITY SCORE
        # ----------------------------------------------------

        severity_score = sum(
            SEVERITY_WEIGHT.get(
                finding["severity"],
                1,
            )
            for finding in findings
        )

        # ----------------------------------------------------
        # OVERALL STATUS
        # ----------------------------------------------------

        if not findings:
            status = "CONSISTENT"

        elif any(
            finding["severity"] == "CRITICAL"
            for finding in findings
        ):
            status = "CRITICAL"

        elif any(
            finding["severity"] == "HIGH"
            for finding in findings
        ):
            status = "REVIEW"

        else:
            status = "MINOR_REVIEW"

        return {
            "status": status,
            "finding_count": len(findings),
            "severity_score": severity_score,
            "findings": findings,
            "engine_version": self.version,
        }


def assess_consistency(
    application: Optional[Dict[str, Any]] = None,
    salary: Optional[Dict[str, Any]] = None,
    bank: Optional[Dict[str, Any]] = None,
    utility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    return ConsistencyEngine().assess(
        application=application,
        salary=salary,
        bank=bank,
        utility=utility,
    )


__all__ = [
    "ConsistencyEngine",
    "assess_consistency",
]