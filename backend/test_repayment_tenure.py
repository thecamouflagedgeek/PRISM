import math

import pytest

from features.repayment_tenure import METHOD, compare_repayment_tenures


def inputs(**overrides):
    result = {"principal": 100000, "annual_interest_rate_percent": 12, "fees": 0,
              "monthly_income": 30000, "monthly_expenses": 15000,
              "existing_monthly_obligations": 0, "max_debt_to_income_ratio": 0.5,
              "tenures_months": [12, 24]}
    result.update(overrides)
    return result


def test_monthly_reducing_balance_reference_case_and_fee_separation():
    result = compare_repayment_tenures(**inputs(tenures_months=[12], fees=500))
    row = result["comparisons"][0]
    assert math.isclose(row["monthly_installment"], 8884.88, abs_tol=0.01)
    assert math.isclose(row["scheduled_total_repayment"], 106618.55, abs_tol=0.02)
    assert math.isclose(row["total_interest"], 6618.55, abs_tol=0.02)
    assert row["fees"] == 500
    assert row["total_cost_including_fees"] == row["scheduled_total_repayment"] + 500
    assert result["method"] == METHOD and result["persisted"] is False


def test_zero_interest_reference_case():
    row = compare_repayment_tenures(**inputs(principal=1200, annual_interest_rate_percent=0,
        tenures_months=[12]))["comparisons"][0]
    assert row["monthly_installment"] == 100
    assert row["total_interest"] == 0


def test_recommendation_is_lowest_cost_only_among_explicitly_affordable_options():
    result = compare_repayment_tenures(**inputs(monthly_expenses=20000,
        existing_monthly_obligations=5000, max_debt_to_income_ratio=0.35))
    assert result["recommendation"]["tenure_months"] == 24
    assert result["comparisons"][0]["affordable_under_supplied_constraints"] is False
    assert result["comparisons"][1]["affordable_under_supplied_constraints"] is True


def test_no_feasible_option_has_no_recommendation():
    result = compare_repayment_tenures(**inputs(monthly_income=10000, monthly_expenses=9000,
        max_debt_to_income_ratio=0.1))
    assert result["status"] == "NO_TENURE_MEETS_SUPPLIED_CONSTRAINTS"
    assert result["recommendation"] is None


@pytest.mark.parametrize("override", [
    {"principal": 0}, {"annual_interest_rate_percent": -1}, {"annual_interest_rate_percent": 101},
    {"monthly_income": 0}, {"fees": -1}, {"tenures_months": []},
    {"tenures_months": [12, 12]}, {"tenures_months": [361]},
])
def test_invalid_inputs_are_rejected(override):
    with pytest.raises(ValueError):
        compare_repayment_tenures(**inputs(**override))


def test_tenure_api_routes_reject_missing_or_wrong_role_without_database_writes():
    from fastapi.testclient import TestClient
    from core.session_store import create_session, _sessions
    from main import app

    borrower = create_session("synthetic-tenure-borrower", user_id=911, application_id=912, role="borrower")
    payload = inputs()
    try:
        with TestClient(app) as client:
            assert client.post("/assess/bank-cashflow/tenure-comparison", json=payload).status_code == 401
            assert client.post("/lender/applications/912/tenure-comparison", json=payload).status_code == 401
            response = client.post("/lender/applications/912/tenure-comparison",
                headers={"session-id": borrower.session_id}, json=payload)
        assert response.status_code == 403
    finally:
        _sessions.pop(borrower.session_id, None)
