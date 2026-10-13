import pandas as pd

from backend.features.financial_health import build_financial_health
from backend.phase2.credit_parser.document_extraction import extract_labeled_fields
from backend.phase2.credit_parser.parser import normalize_amount, normalize_currency, normalize_month


def test_monthly_indicators_are_separate_and_omit_narration():
    rows = pd.DataFrame([
        {"date": "01/01/2026", "amount": 1000, "type": "CR", "narration": "SALARY", "closing_balance": 1000},
        {"date": "15/01/2026", "amount": 200, "type": "DR", "narration": "HOME LOAN EMI", "closing_balance": 800},
        {"date": "01/02/2026", "amount": 1200, "type": "CR", "narration": "SALARY", "closing_balance": 2000},
        {"date": "15/02/2026", "amount": 250, "type": "DR", "narration": "HOME LOAN EMI", "closing_balance": 1750},
        {"date": "20/02/2026", "amount": 40, "type": "DR", "narration": "PAYMENT RETURNED", "closing_balance": 1710},
    ])
    result = build_financial_health(rows, extraction={"method": "native_text", "page_count": 2})
    assert result["status"] == "AVAILABLE"
    assert result["separate_from_frozen_credit_pd"] is True
    assert result["months_observed"] == 2
    assert result["monthly"][0]["income_total"] == 1000
    assert result["monthly"][0]["expense_total"] == 200
    assert result["possible_debt_payments"]["matching_transaction_count"] == 2
    assert result["explicit_returned_payment_indicators"]["matching_transaction_count"] == 1
    assert result["salary_labelled_credits"]["months"] == 2
    assert result["recurring_obligation_patterns"]["pattern_count"] == 1
    assert "narration" not in repr(result)
    assert "HOME LOAN" not in repr(result)


def test_missing_or_invalid_transactions_are_unavailable_not_zero_activity():
    assert build_financial_health(None)["status"] == "UNAVAILABLE"
    malformed = pd.DataFrame([{"date": "not a date", "amount": "x", "type": "?"}])
    result = build_financial_health(malformed)
    assert result["status"] == "UNAVAILABLE"
    assert result["transaction_count"] == 0


def test_card_label_variants_keep_page_line_provenance_and_normalize_formats():
    fields, gaps = extract_labeled_fields(
        "Billing Date: 31/03/2026\nIssuer: Example\n\f\n"
        "Card No: ****1234\nCurrency: ₹\nNew Balance: ₹ 1,23,456.00\n"
        "Payment Received for Statement: ₹ 20,000.00\nPayment Status: CURRENT\n"
        "Delinquency Severity: 0"
    )
    assert fields["statement_month"] == "31/03/2026"
    assert fields["statement_balance"] == "₹ 1,23,456.00"
    assert fields["_field_provenance"]["statement_balance"] == {"page": 2, "line": 3}
    assert not any("statement_balance" in issue or "payment_amount" in issue for issue in gaps)
    assert normalize_month(fields["statement_month"]) == "2026-03"
    assert normalize_currency(fields["currency"]) == "INR"
    assert str(normalize_amount(fields["statement_balance"])) == "123456.00"
