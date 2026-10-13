import pandas as pd

from features.bank_health_index import calculate_bank_health_index, simulate_bank_health


def transactions(income=1000, expense=500):
    rows = []
    for month, balance in [("2025-01", 1200), ("2025-02", 1400), ("2025-03", 1600)]:
        rows.extend([
            {"date": f"{month}-05", "amount": income, "type": "CR", "narration": "salary", "closing_balance": balance},
            {"date": f"{month}-20", "amount": expense, "type": "DR", "narration": "rent", "closing_balance": balance-500},
        ])
    return pd.DataFrame(rows)


def evidence(**overrides):
    return {"account_linked": True, "balance_reconciled": True,
            "duplicate_ambiguity": False, "page_coverage_complete": True,
            "complete_month_coverage": True, "transaction_order_valid": True,
            "non_cashflow_adjustments_clear": True,
            "extraction_quality_min": .95, **overrides}


def test_eligible_index_has_no_pd_and_component_arithmetic_matches():
    result = calculate_bank_health_index(transactions(), currency="INR", evidence=evidence())
    assert result["scoreable"] and result["status"] == "SCORED"
    assert result["pd"] is None and result["risk_tier"] is None
    assert 300 <= result["score"] <= 900
    assert 300 + sum(x["score_contribution"] for x in result["feature_contributions"]) == result["score"]


def test_insufficient_months_or_unlinked_account_never_scores():
    result = calculate_bank_health_index(transactions().iloc[:2], currency="INR", evidence=evidence())
    assert not result["scoreable"]
    result = calculate_bank_health_index(transactions(), currency="INR", evidence=evidence(account_linked=False))
    assert not result["scoreable"]


def test_better_cashflow_improves_index_when_other_inputs_fixed():
    weak = calculate_bank_health_index(transactions(1000, 800), currency="INR", evidence=evidence())
    strong = calculate_bank_health_index(transactions(1500, 500), currency="INR", evidence=evidence())
    assert strong["score"] > weak["score"]


def test_monthly_scores_are_derived_from_each_months_observed_patterns():
    df = pd.DataFrame([
        {"date":"2025-01-05","amount":1000,"type":"CR","narration":"income","closing_balance":1000},
        {"date":"2025-01-20","amount":100,"type":"DR","narration":"expense","closing_balance":900},
        {"date":"2025-02-05","amount":1000,"type":"CR","narration":"income","closing_balance":20},
        {"date":"2025-02-20","amount":1200,"type":"DR","narration":"expense","closing_balance":10},
    ])
    result = calculate_bank_health_index(df, currency="INR", evidence=evidence())
    by_month = {item["month"]:item for item in result["monthly"]}
    assert by_month["2025-01"]["observed_pattern_score"] is not None
    assert by_month["2025-02"]["observed_pattern_score"] is not None
    assert by_month["2025-01"]["observed_pattern_score"] > by_month["2025-02"]["observed_pattern_score"]
    assert by_month["2025-01"]["available_pattern_count"] >= 2


def test_what_if_is_hypothetical_and_does_not_mutate_assessment():
    baseline = calculate_bank_health_index(transactions(), currency="INR", evidence=evidence())
    original = baseline["score"]
    hypothetical = simulate_bank_health(baseline, {"monthly_income": 1500, "monthly_expenses": 500,
        "monthly_debt_obligations": 100, "average_balance": 2000, "income_volatility": .1})
    assert hypothetical["hypothetical_only"] and hypothetical["pd"] is None
    assert hypothetical["score"] > original
    assert baseline["score"] == original
