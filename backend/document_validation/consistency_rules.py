"""
PRISM — Cross-Document Consistency Rules

Checks whether information extracted from different borrower
documents is internally consistent.

This module does NOT calculate credit risk or fraud score.

It produces document-consistency findings that can later be
consumed by the assessment/decision layer.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


# ============================================================
# CONFIGURATION
# ============================================================

INCOME_VARIANCE_THRESHOLD = 0.15
IDENTITY_FIELDS = (
    "name",
    "pan",
    "account_number",
    "employee_id",
)

RULE_CODES = {
    "NAME_MISMATCH": "CONS-001",
    "PAN_MISMATCH": "CONS-002",
    "ACCOUNT_MISMATCH": "CONS-003",
    "INCOME_MISMATCH": "CONS-004",
    "EMPLOYMENT_MISMATCH": "CONS-005",
    "DATE_MISMATCH": "CONS-006",
    "STATEMENT_PERIOD_GAP": "CONS-007",
}


# ============================================================
# HELPERS
# ============================================================

def _clean(value: Any) -> Optional[str]:
    """
    Normalize a value for comparison.

    Returns None when the value is missing.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value.upper()


def _numeric(value: Any) -> Optional[float]:
    """
    Safely convert a value to float.
    """

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _result(
    code: str,
    field: str,
    severity: str,
    message: str,
    sources: list[str],
) -> Dict[str, Any]:

    return {
        "rule_code": code,
        "field": field,
        "severity": severity,
        "message": message,
        "sources": sources,
    }


# ============================================================
# IDENTITY CONSISTENCY
# ============================================================

def check_name_consistency(
    application: Dict[str, Any],
    salary: Optional[Dict[str, Any]],
    bank: Optional[Dict[str, Any]],
    utility: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    values = {
        "application": _clean(application.get("name")),
        "salary": _clean((salary or {}).get("name")),
        "bank": _clean((bank or {}).get("name")),
        "utility": _clean((utility or {}).get("name")),
    }

    present = {
        source: value
        for source, value in values.items()
        if value is not None
    }

    if len(present) < 2:
        return None

    unique_values = set(present.values())

    if len(unique_values) == 1:
        return None

    return _result(
        RULE_CODES["NAME_MISMATCH"],
        "name",
        "HIGH",
        "Borrower name is inconsistent across submitted documents.",
        list(present.keys()),
    )


def check_pan_consistency(
    application: Dict[str, Any],
    salary: Optional[Dict[str, Any]],
    bank: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    values = {
        "application": _clean(application.get("pan")),
        "salary": _clean((salary or {}).get("pan")),
        "bank": _clean((bank or {}).get("pan")),
    }

    present = {
        source: value
        for source, value in values.items()
        if value is not None
    }

    if len(present) < 2:
        return None

    if len(set(present.values())) == 1:
        return None

    return _result(
        RULE_CODES["PAN_MISMATCH"],
        "pan",
        "CRITICAL",
        "PAN identity is inconsistent across submitted documents.",
        list(present.keys()),
    )


def check_account_consistency(
    application: Dict[str, Any],
    bank: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    application_account = _clean(
        application.get("account_number")
    )

    bank_account = _clean(
        (bank or {}).get("account_number")
    )

    if application_account is None or bank_account is None:
        return None

    if application_account == bank_account:
        return None

    return _result(
        RULE_CODES["ACCOUNT_MISMATCH"],
        "account_number",
        "HIGH",
        "Bank account number does not match the application record.",
        ["application", "bank"],
    )


# ============================================================
# INCOME CONSISTENCY
# ============================================================

def check_income_consistency(
    application: Dict[str, Any],
    salary: Optional[Dict[str, Any]],
    bank: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    declared_income = _numeric(
        application.get("monthly_income")
    )

    salary_income = _numeric(
        (salary or {}).get("net_salary")
    )

    bank_income = _numeric(
        (bank or {}).get("average_salary_credit")
    )

    observations = [
        value
        for value in (
            declared_income,
            salary_income,
            bank_income,
        )
        if value is not None
    ]

    if len(observations) < 2:
        return None

    reference = observations[0]

    if reference == 0:
        return None

    for value in observations[1:]:
        variance = abs(value - reference) / abs(reference)

        if variance > INCOME_VARIANCE_THRESHOLD:

            return _result(
                RULE_CODES["INCOME_MISMATCH"],
                "monthly_income",
                "HIGH",
                (
                    "Declared and document-derived income differ "
                    f"by more than {INCOME_VARIANCE_THRESHOLD:.0%}."
                ),
                ["application", "salary", "bank"],
            )

    return None


# ============================================================
# EMPLOYMENT CONSISTENCY
# ============================================================

def check_employment_consistency(
    application: Dict[str, Any],
    salary: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    application_employer = _clean(
        application.get("employer")
    )

    salary_employer = _clean(
        (salary or {}).get("employer")
    )

    if (
        application_employer is None
        or salary_employer is None
    ):
        return None

    if application_employer == salary_employer:
        return None

    return _result(
        RULE_CODES["EMPLOYMENT_MISMATCH"],
        "employer",
        "MEDIUM",
        "Employer information differs between application and salary document.",
        ["application", "salary"],
    )


# ============================================================
# DOCUMENT DATE CONSISTENCY
# ============================================================

def check_statement_period(
    bank: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    if not bank:
        return None

    start_date = bank.get("statement_start_date")
    end_date = bank.get("statement_end_date")

    if start_date is None or end_date is None:
        return None

    if str(start_date) > str(end_date):

        return _result(
            RULE_CODES["DATE_MISMATCH"],
            "statement_period",
            "HIGH",
            "Bank statement start date occurs after end date.",
            ["bank"],
        )

    return None


# ============================================================
# RULE COLLECTION
# ============================================================

CONSISTENCY_RULES = (
    check_name_consistency,
    check_pan_consistency,
    check_account_consistency,
    check_income_consistency,
    check_employment_consistency,
    check_statement_period,
)


__all__ = [
    "check_name_consistency",
    "check_pan_consistency",
    "check_account_consistency",
    "check_income_consistency",
    "check_employment_consistency",
    "check_statement_period",
    "CONSISTENCY_RULES",
]