"""
PRISM - Document Validation Unit Tests
"""

import pytest

from document_validation.validation_engine import DocumentValidationEngine

# ============================================================
# HELPERS
# ============================================================

def clean_bank():
    return {
        "account_number": "1234567890",
        "transactions": [
            {
                "date": "2026-09-01",
                "amount": 50000,
                "type": "CR",
            },
            {
                "date": "2026-09-02",
                "amount": 10000,
                "type": "DR",
            },
        ],
        "closing_balance": 40000,
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
    }


def clean_salary():
    return {
        "employee_name": "HAZEL SEQUERIA",
        "employer": "ABC TECHNOLOGIES",
        "salary_period": "September 2026",
        "gross_salary": 80000,
        "net_salary": 68000,
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
    }


def clean_utility():
    return {
        "customer_name": "HAZEL SEQUERIA",
        "billing_period": "September 2026",
        "amount": 2500,
        "customer_id": "CUST123",
        "period_start": "2026-09-01",
        "period_end": "2026-09-30",
    }


def clean_application():
    return {
        "borrower_name": "HAZEL SEQUERIA",
        "pan": "ABCDE1234F",
        "account_number": "1234567890",
        "declared_income": 68000,
    }


# ============================================================
# REQUIRED FIELD TESTS
# ============================================================

def test_clean_bank_document():

    engine = DocumentValidationEngine()

    result = engine.validate_single(
        "BANK",
        clean_bank(),
    )

    assert result["status"] == "VERIFIED"
    assert result["finding_count"] == 0


def test_missing_bank_transactions():

    engine = DocumentValidationEngine()

    bank = clean_bank()

    del bank["transactions"]

    result = engine.validate_single(
        "BANK",
        bank,
    )

    assert result["status"] == "REVIEW"

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "MISSING_FIELD" in codes


def test_clean_salary_document():

    engine = DocumentValidationEngine()

    result = engine.validate_single(
        "SALARY",
        clean_salary(),
    )

    assert result["status"] == "VERIFIED"


def test_net_salary_greater_than_gross():

    engine = DocumentValidationEngine()

    salary = clean_salary()

    salary["net_salary"] = 90000

    result = engine.validate_single(
        "SALARY",
        salary,
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "NET_GREATER_THAN_GROSS" in codes
    assert result["status"] == "REVIEW"


def test_clean_utility_document():

    engine = DocumentValidationEngine()

    result = engine.validate_single(
        "UTILITY",
        clean_utility(),
    )

    assert result["status"] == "VERIFIED"


# ============================================================
# BANK TRANSACTION TESTS
# ============================================================

def test_invalid_transaction_amount():

    engine = DocumentValidationEngine()

    bank = clean_bank()

    bank["transactions"][0]["amount"] = "NOT_A_NUMBER"

    result = engine.validate_single(
        "BANK",
        bank,
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "INVALID_TRANSACTION_AMOUNT" in codes


def test_non_chronological_transactions():

    engine = DocumentValidationEngine()

    bank = clean_bank()

    bank["transactions"][1]["date"] = "2026-08-01"

    result = engine.validate_single(
        "BANK",
        bank,
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "NON_CHRONOLOGICAL_TRANSACTIONS" in codes


# ============================================================
# CROSS-DOCUMENT TESTS
# ============================================================

def test_matching_identity():

    engine = DocumentValidationEngine()

    documents = {
        "APPLICATION": clean_application(),
        "BANK": clean_bank(),
    }

    result = engine.validate_cross_documents(
        documents
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "IDENTITY_MISMATCH" not in codes


def test_identity_mismatch():

    engine = DocumentValidationEngine()

    application = clean_application()

    bank = clean_bank()

    bank["account_number"] = "9999999999"

    documents = {
        "APPLICATION": application,
        "BANK": bank,
    }

    result = engine.validate_cross_documents(
        documents
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "ACCOUNT_MISMATCH" in codes
    assert result["status"] == "REVIEW"


def test_name_mismatch():

    engine = DocumentValidationEngine()

    documents = {
        "APPLICATION": clean_application(),
        "SALARY": clean_salary(),
    }

    documents["SALARY"]["employee_name"] = (
        "DIFFERENT PERSON"
    )

    result = engine.validate_cross_documents(
        documents
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "NAME_MISMATCH" in codes


def test_income_consistency():

    engine = DocumentValidationEngine()

    documents = {
        "APPLICATION": clean_application(),
        "SALARY": clean_salary(),
    }

    result = engine.validate_cross_documents(
        documents
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "INCOME_MISMATCH" not in codes


def test_income_mismatch():

    engine = DocumentValidationEngine()

    documents = {
        "APPLICATION": clean_application(),
        "SALARY": clean_salary(),
    }

    documents["APPLICATION"]["declared_income"] = 120000

    result = engine.validate_cross_documents(
        documents
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "INCOME_MISMATCH" in codes


# ============================================================
# FULL ASSESSMENT
# ============================================================

def test_full_clean_assessment():

    engine = DocumentValidationEngine()

    documents = {
        "APPLICATION": clean_application(),
        "BANK": clean_bank(),
        "SALARY": clean_salary(),
        "UTILITY": clean_utility(),
    }

    result = engine.assess(
        documents
    )

    assert result["document_status"] == "VERIFIED"
    assert result["finding_count"] == 0


def test_full_assessment_with_multiple_issues():

    engine = DocumentValidationEngine()

    documents = {
        "APPLICATION": clean_application(),
        "BANK": clean_bank(),
        "SALARY": clean_salary(),
    }

    documents["APPLICATION"]["declared_income"] = 150000

    documents["BANK"]["account_number"] = (
        "9999999999"
    )

    result = engine.assess(
        documents
    )

    codes = {
        finding["code"]
        for finding in result["findings"]
    }

    assert "ACCOUNT_MISMATCH" in codes
    assert "INCOME_MISMATCH" in codes

    assert result["document_status"] == "REVIEW"


if __name__ == "__main__":
    pytest.main(
        [__file__, "-v"]
    )