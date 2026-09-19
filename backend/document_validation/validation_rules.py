"""
PRISM - Document Validation Rules

P1 Document Intelligence Layer.

This module contains deterministic document-level and
cross-document validation rules.

Important:
- This module does NOT calculate credit risk.
- This module does NOT calculate fraud score.
- This module does NOT modify scorecard artifacts.
- Rules return structured validation findings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import math
import re


# ============================================================
# CONSTANTS
# ============================================================

DOCUMENT_TYPES = {
    "BANK",
    "SALARY",
    "UTILITY",
    "APPLICATION",
}


# ============================================================
# GENERIC HELPERS
# ============================================================

def _is_missing(value: Any) -> bool:
    """
    Determine whether a value should be treated as missing.
    """

    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    return False


def _to_float(value: Any) -> Optional[float]:
    """
    Safely convert a value to float.
    """

    if _is_missing(value):
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def _normalize_text(value: Any) -> Optional[str]:
    """
    Normalize text for comparison.
    """

    if _is_missing(value):
        return None

    text = str(value).strip().upper()

    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip() or None


def _normalize_identifier(value: Any) -> Optional[str]:
    """
    Normalize identifiers such as PAN/account/customer IDs.
    """

    if _is_missing(value):
        return None

    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper(),
    ) or None


def _parse_date(value: Any) -> Optional[datetime]:
    """
    Parse common date formats.
    """

    if _is_missing(value):
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def _add_finding(
    findings: List[Dict[str, Any]],
    code: str,
    category: str,
    severity: str,
    message: str,
    field: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append one standardized validation finding.
    """

    finding = {
        "code": code,
        "category": category,
        "severity": severity,
        "message": message,
    }

    if field is not None:
        finding["field"] = field

    if evidence:
        finding["evidence"] = evidence

    findings.append(finding)


# ============================================================
# REQUIRED FIELD RULES
# ============================================================

REQUIRED_FIELDS = {
    "BANK": [
        "transactions",
        "closing_balance",
    ],
    "SALARY": [
        "employee_name",
        "employer",
        "salary_period",
        "gross_salary",
        "net_salary",
    ],
    "UTILITY": [
        "customer_name",
        "billing_period",
        "amount",
    ],
}


def validate_required_fields(
    document_type: str,
    document: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Check mandatory extracted fields.
    """

    findings: List[Dict[str, Any]] = []

    required = REQUIRED_FIELDS.get(
        document_type.upper(),
        [],
    )

    for field in required:

        value = document.get(field)

        if _is_missing(value):

            _add_finding(
                findings=findings,
                code="MISSING_FIELD",
                category="COMPLETENESS",
                severity="MEDIUM",
                message=f"Required field '{field}' is missing.",
                field=field,
            )

    return findings


# ============================================================
# BANK DOCUMENT RULES
# ============================================================

def validate_bank_document(
    document: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Validate bank-statement-specific fields.
    """

    findings: List[Dict[str, Any]] = []

    transactions = document.get("transactions")

    if transactions is not None and not isinstance(
        transactions,
        list,
    ):
        _add_finding(
            findings,
            "INVALID_TRANSACTIONS",
            "FORMAT",
            "HIGH",
            "Bank transactions must be represented as a list.",
            field="transactions",
        )

    closing_balance = _to_float(
        document.get("closing_balance")
    )

    if (
        document.get("closing_balance") is not None
        and closing_balance is None
    ):
        _add_finding(
            findings,
            "INVALID_CLOSING_BALANCE",
            "FORMAT",
            "HIGH",
            "Closing balance is not a valid numeric value.",
            field="closing_balance",
        )

    opening_balance = _to_float(
        document.get("opening_balance")
    )

    if (
        document.get("opening_balance") is not None
        and opening_balance is None
    ):
        _add_finding(
            findings,
            "INVALID_OPENING_BALANCE",
            "FORMAT",
            "MEDIUM",
            "Opening balance is not a valid numeric value.",
            field="opening_balance",
        )

    # --------------------------------------------------------
    # Transaction-level validation
    # --------------------------------------------------------

    if isinstance(transactions, list):

        previous_date: Optional[datetime] = None

        for index, transaction in enumerate(transactions):

            if not isinstance(transaction, dict):

                _add_finding(
                    findings,
                    "INVALID_TRANSACTION_ROW",
                    "FORMAT",
                    "HIGH",
                    f"Transaction {index} is not a structured record.",
                    field=f"transactions[{index}]",
                )

                continue

            amount = _to_float(
                transaction.get("amount")
            )

            if amount is None or amount < 0:

                _add_finding(
                    findings,
                    "INVALID_TRANSACTION_AMOUNT",
                    "FORMAT",
                    "HIGH",
                    f"Transaction {index} has an invalid amount.",
                    field=f"transactions[{index}].amount",
                )

            tx_date = _parse_date(
                transaction.get("date")
            )

            if transaction.get("date") is not None:

                if tx_date is None:

                    _add_finding(
                        findings,
                        "INVALID_TRANSACTION_DATE",
                        "FORMAT",
                        "MEDIUM",
                        f"Transaction {index} has an invalid date.",
                        field=f"transactions[{index}].date",
                    )

                elif previous_date is not None and tx_date < previous_date:

                    _add_finding(
                        findings,
                        "NON_CHRONOLOGICAL_TRANSACTIONS",
                        "CONSISTENCY",
                        "MEDIUM",
                        "Transaction dates are not chronological.",
                        field="transactions",
                    )

                if tx_date is not None:
                    previous_date = tx_date

    return findings


# ============================================================
# SALARY DOCUMENT RULES
# ============================================================

def validate_salary_document(
    document: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Validate salary-slip-specific fields.
    """

    findings: List[Dict[str, Any]] = []

    gross = _to_float(
        document.get("gross_salary")
    )

    net = _to_float(
        document.get("net_salary")
    )

    if gross is not None and gross <= 0:

        _add_finding(
            findings,
            "INVALID_GROSS_SALARY",
            "FORMAT",
            "HIGH",
            "Gross salary must be greater than zero.",
            field="gross_salary",
        )

    if net is not None and net <= 0:

        _add_finding(
            findings,
            "INVALID_NET_SALARY",
            "FORMAT",
            "HIGH",
            "Net salary must be greater than zero.",
            field="net_salary",
        )

    if (
        gross is not None
        and net is not None
        and net > gross
    ):

        _add_finding(
            findings,
            "NET_GREATER_THAN_GROSS",
            "CONSISTENCY",
            "HIGH",
            "Net salary cannot exceed gross salary.",
            evidence={
                "gross_salary": gross,
                "net_salary": net,
            },
        )

    return findings


# ============================================================
# UTILITY DOCUMENT RULES
# ============================================================

def validate_utility_document(
    document: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Validate utility-bill-specific fields.
    """

    findings: List[Dict[str, Any]] = []

    amount = _to_float(
        document.get("amount")
    )

    if amount is not None and amount < 0:

        _add_finding(
            findings,
            "NEGATIVE_UTILITY_AMOUNT",
            "FORMAT",
            "HIGH",
            "Utility amount cannot be negative.",
            field="amount",
        )

    return findings


# ============================================================
# DOCUMENT PERIOD RULES
# ============================================================

def validate_document_period(
    document_type: str,
    document: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Validate basic document period information.
    """

    findings: List[Dict[str, Any]] = []

    start = _parse_date(
        document.get("period_start")
    )

    end = _parse_date(
        document.get("period_end")
    )

    if (
        document.get("period_start") is not None
        and start is None
    ):

        _add_finding(
            findings,
            "INVALID_PERIOD_START",
            "FORMAT",
            "MEDIUM",
            "Document period start is invalid.",
            field="period_start",
        )

    if (
        document.get("period_end") is not None
        and end is None
    ):

        _add_finding(
            findings,
            "INVALID_PERIOD_END",
            "FORMAT",
            "MEDIUM",
            "Document period end is invalid.",
            field="period_end",
        )

    if (
        start is not None
        and end is not None
        and start > end
    ):

        _add_finding(
            findings,
            "INVALID_DOCUMENT_PERIOD",
            "CONSISTENCY",
            "HIGH",
            "Document period start occurs after period end.",
            evidence={
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
            },
        )

    return findings


# ============================================================
# IDENTITY CONSISTENCY
# ============================================================

IDENTITY_FIELDS = [
    "pan",
    "account_number",
    "customer_id",
    "borrower_id",
]


def validate_identity_consistency(
    documents: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Compare shared identity identifiers across documents.

    Only fields that are actually present are compared.
    """

    findings: List[Dict[str, Any]] = []

    for field in IDENTITY_FIELDS:

        values = []

        for document_type, document in documents.items():

            value = document.get(field)

            normalized = _normalize_identifier(
                value
            )

            if normalized:

                values.append(
                    {
                        "document_type": document_type,
                        "value": normalized,
                    }
                )

        if len(values) < 2:
            continue

        unique_values = {
            item["value"]
            for item in values
        }

        if len(unique_values) > 1:

            _add_finding(
                findings,
                "IDENTITY_MISMATCH",
                "CROSS_DOCUMENT",
                "HIGH",
                f"Identifier '{field}' differs across submitted documents.",
                field=field,
                evidence={
                    "values": values,
                },
            )

    return findings


# ============================================================
# NAME CONSISTENCY
# ============================================================

NAME_FIELDS = [
    "name",
    "employee_name",
    "customer_name",
    "borrower_name",
]


def validate_name_consistency(
    documents: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Compare names across documents.
    """

    findings: List[Dict[str, Any]] = []

    values = []

    for document_type, document in documents.items():

        value = None

        for field in NAME_FIELDS:

            if not _is_missing(document.get(field)):

                value = document.get(field)
                break

        normalized = _normalize_text(value)

        if normalized:

            values.append(
                {
                    "document_type": document_type,
                    "name": normalized,
                }
            )

    if len(values) < 2:
        return findings

    unique_names = {
        item["name"]
        for item in values
    }

    if len(unique_names) > 1:

        _add_finding(
            findings,
            "NAME_MISMATCH",
            "CROSS_DOCUMENT",
            "HIGH",
            "Borrower name differs across submitted documents.",
            field="name",
            evidence={
                "values": values,
            },
        )

    return findings


# ============================================================
# ACCOUNT CONSISTENCY
# ============================================================

def validate_account_consistency(
    documents: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Compare account numbers across documents where available.
    """

    findings: List[Dict[str, Any]] = []

    values = []

    for document_type, document in documents.items():

        value = document.get("account_number")

        normalized = _normalize_identifier(
            value
        )

        if normalized:

            values.append(
                {
                    "document_type": document_type,
                    "account_number": normalized,
                }
            )

    if len(values) < 2:
        return findings

    unique_accounts = {
        item["account_number"]
        for item in values
    }

    if len(unique_accounts) > 1:

        _add_finding(
            findings,
            "ACCOUNT_MISMATCH",
            "CROSS_DOCUMENT",
            "HIGH",
            "Bank account identifier differs across submitted documents.",
            field="account_number",
            evidence={
                "values": values,
            },
        )

    return findings


# ============================================================
# INCOME CONSISTENCY
# ============================================================

def _extract_declared_income(
    document: Dict[str, Any],
) -> Optional[float]:

    candidates = [
        "declared_income",
        "monthly_income",
        "income",
    ]

    for field in candidates:

        value = _to_float(
            document.get(field)
        )

        if value is not None:
            return value

    return None


def _extract_salary_income(
    document: Dict[str, Any],
) -> Optional[float]:

    candidates = [
        "net_salary",
        "gross_salary",
        "monthly_salary",
    ]

    for field in candidates:

        value = _to_float(
            document.get(field)
        )

        if value is not None:
            return value

    return None


def _extract_bank_income(
    document: Dict[str, Any],
) -> Optional[float]:

    candidates = [
        "salary_credits",
        "monthly_salary_credit",
        "monthly_income",
        "salary_income",
    ]

    for field in candidates:

        value = _to_float(
            document.get(field)
        )

        if value is not None:
            return value

    return None


def _relative_difference(
    a: float,
    b: float,
) -> float:

    denominator = max(
        abs(a),
        abs(b),
        1.0,
    )

    return abs(a - b) / denominator


def validate_income_consistency(
    documents: Dict[str, Dict[str, Any]],
    tolerance: float = 0.15,
) -> List[Dict[str, Any]]:
    """
    Compare declared, salary-slip and bank-derived income.

    tolerance=0.15 means a 15% relative difference is allowed.
    """

    findings: List[Dict[str, Any]] = []

    values = []

    application = documents.get("APPLICATION")

    if application:

        income = _extract_declared_income(
            application
        )

        if income is not None:
            values.append(
                ("APPLICATION", income)
            )

    salary = documents.get("SALARY")

    if salary:

        income = _extract_salary_income(
            salary
        )

        if income is not None:
            values.append(
                ("SALARY", income)
            )

    bank = documents.get("BANK")

    if bank:

        income = _extract_bank_income(
            bank
        )

        if income is not None:
            values.append(
                ("BANK", income)
            )

    if len(values) < 2:
        return findings

    reference_type, reference_value = values[0]

    for document_type, value in values[1:]:

        difference = _relative_difference(
            reference_value,
            value,
        )

        if difference > tolerance:

            _add_finding(
                findings,
                "INCOME_MISMATCH",
                "CROSS_DOCUMENT",
                "HIGH",
                "Income values differ beyond the configured tolerance.",
                field="income",
                evidence={
                    "reference_document": reference_type,
                    "reference_value": reference_value,
                    "comparison_document": document_type,
                    "comparison_value": value,
                    "relative_difference": round(
                        difference,
                        4,
                    ),
                    "tolerance": tolerance,
                },
            )

    return findings


# ============================================================
# MASTER DOCUMENT VALIDATION
# ============================================================

def validate_document(
    document_type: str,
    document: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Execute all applicable document-level validation rules.
    """

    document_type = document_type.upper()

    findings: List[Dict[str, Any]] = []

    findings.extend(
        validate_required_fields(
            document_type,
            document,
        )
    )

    findings.extend(
        validate_document_period(
            document_type,
            document,
        )
    )

    if document_type == "BANK":

        findings.extend(
            validate_bank_document(
                document
            )
        )

    elif document_type == "SALARY":

        findings.extend(
            validate_salary_document(
                document
            )
        )

    elif document_type == "UTILITY":

        findings.extend(
            validate_utility_document(
                document
            )
        )

    return findings


# ============================================================
# CROSS-DOCUMENT MASTER VALIDATION
# ============================================================

def validate_cross_documents(
    documents: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Execute cross-document consistency rules.
    """

    findings: List[Dict[str, Any]] = []

    findings.extend(
        validate_identity_consistency(
            documents
        )
    )

    findings.extend(
        validate_name_consistency(
            documents
        )
    )

    findings.extend(
        validate_account_consistency(
            documents
        )
    )

    findings.extend(
        validate_income_consistency(
            documents
        )
    )

    return findings


__all__ = [
    "validate_document",
    "validate_cross_documents",
    "validate_required_fields",
    "validate_bank_document",
    "validate_salary_document",
    "validate_utility_document",
]