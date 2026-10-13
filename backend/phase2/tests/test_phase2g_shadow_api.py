"""Phase 2G API contract tests; isolated app mounts only the experimental router."""
import json
from pathlib import Path
import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from phase2.shadow_api.routes import router, ShadowSimulationRequest, FrozenFeatureVector, shadow_simulate
from route.assessment_routes import mark_as_pending_frozen_scorecard

PHASE2 = Path(__file__).parents[1]
FIXTURE = PHASE2 / "outputs" / "phase2e" / "golden_fixture.json"


def make_client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def golden(client):
    return client.get("/experimental/shadow-golden-request").json()


def test_experimental_feature_flag_off_disables_route_without_scoring(monkeypatch):
    client = make_client()
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    body = golden(client)
    monkeypatch.delenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", raising=False)
    response = client.get("/experimental/shadow-golden-request")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "EXPERIMENTAL_FEATURE_DISABLED"
    score_response = client.post("/experimental/shadow-assess", json=body)
    assert score_response.status_code == 404
    assert score_response.json()["detail"]["code"] == "EXPERIMENTAL_FEATURE_DISABLED"


def test_feature_flag_on_enables_golden_fixture_and_endpoint(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    response = client.get("/experimental/shadow-golden-request")
    assert response.status_code == 200
    assert len(response.json()["statements"]) == 6
    assert len(response.json()["repayment_history"]) == 6


def test_shadow_simulation_reuses_frozen_model_and_does_not_persist(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    baseline = {"recent_delinquency_level": 3, "months_with_delinquency": 3,
        "payment_to_statement_ratio": .5, "mean_statement_balance": 350}
    scenario = {**baseline, "recent_delinquency_level": 0,
        "months_with_delinquency": 0, "payment_to_statement_ratio": .8}
    output = shadow_simulate(ShadowSimulationRequest(
        baseline=FrozenFeatureVector(**baseline), scenario=FrozenFeatureVector(**scenario)))
    assert output["status"] == "HYPOTHETICAL_ONLY"
    assert output["persisted"] is False
    assert output["baseline"]["scorecard"]["raw_pd"] == pytest.approx(.802589175756118, abs=1e-12)
    assert output["scenario"]["artifact_sha256"] == output["baseline"]["artifact_sha256"]
    assert output["scenario"]["scorecard"]["raw_pd"] < output["baseline"]["scorecard"]["raw_pd"]
    assert output["scenario"]["scorecard"]["experimental_shadow_score"] > output["baseline"]["scorecard"]["experimental_shadow_score"]
    assert output["delta"]["score"] == pytest.approx(
        output["scenario"]["scorecard"]["experimental_shadow_score"] -
        output["baseline"]["scorecard"]["experimental_shadow_score"])
    assert set(output["baseline"]["feature_trace"]) == {
        "recent_delinquency_level", "months_with_delinquency",
        "payment_to_statement_ratio", "mean_statement_balance"}


def test_score_scaling_is_deterministic_and_monotone():
    from phase2.shadow_scorecard.score_scaling import score_from_pd
    score = score_from_pd(0.2)[1]
    assert score_from_pd(0.2)[1] == score
    assert score_from_pd(0.1)[1] > score > score_from_pd(0.4)[1]


def test_shadow_simulation_http_contract_rejects_out_of_bin_values(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    body = {"baseline": {"recent_delinquency_level": 3, "months_with_delinquency": 3,
        "payment_to_statement_ratio": .5, "mean_statement_balance": 350},
        "scenario": {"recent_delinquency_level": 10, "months_with_delinquency": 0,
            "payment_to_statement_ratio": .8, "mean_statement_balance": 1e100}}
    response = make_client().post("/experimental/shadow-simulate", json=body)
    assert response.status_code == 422
    assert "recent_delinquency_level" in str(response.json()["detail"])


def test_golden_api_reproduces_phase2f_output_and_reason_order(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    body = golden(client)
    response = client.post("/experimental/shadow-assess", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "EXPERIMENTAL_SHADOW_SCORE"
    assert result["decision_use"] == "NOT_FOR_CREDIT_DECISION"
    assert result["features"] == {"recent_delinquency_level": 3, "months_with_delinquency": 3,
        "payment_to_statement_ratio": .5, "mean_statement_balance": 350}
    assert result["scorecard"]["raw_pd"] == pytest.approx(.802589175756118, abs=1e-12)
    assert result["scorecard"]["good_bad_odds"] == pytest.approx(.245967464061426, abs=1e-12)
    assert result["scorecard"]["experimental_shadow_score"] == pytest.approx(282.730565122, abs=1e-9)
    for field in ("assessment_id", "assessment_status", "model_version", "score",
                  "probability_of_default", "risk_tier", "feature_coverage", "feature_values",
                  "woe_values", "feature_contributions", "improvement_recommendations",
                  "document_findings", "fraud_findings", "assessment_timestamp"):
        assert field in result
    assert result["assessment_status"] == "SCORED"
    assert result["score"] == pytest.approx(result["scorecard"]["experimental_shadow_score"])
    assert result["probability_of_default"] == pytest.approx(result["scorecard"]["raw_pd"])
    assert result["feature_coverage"] == 1.0
    assert result["risk_tier"] is None
    assert [r["label"] for r in result["reason_codes"]] == ["Recent repayment delinquency",
        "Repeated repayment delinquency", "Average statement balance"]
    assert result["scorecard"]["pdo_presentation_only"] is True
    assert "decision" not in result


def test_statement_only_and_consent_failures_have_specific_blockers(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    body = golden(client)
    body["repayment_history"] = []
    statement_only = client.post("/experimental/shadow-assess", json=body).json()
    assert "MISSING_REPAYMENT_STATUS_EVIDENCE" in statement_only["eligibility"]["blocking_reasons"]
    assert statement_only["scorecard"] is None
    body = golden(client); body["consent"] = None
    assert "CONSENT_REQUIRED" in client.post("/experimental/shadow-assess", json=body).json()["eligibility"]["blocking_reasons"]
    body = golden(client); body["consent"]["state"] = "WITHDRAWN"
    assert "CONSENT_WITHDRAWN" in client.post("/experimental/shadow-assess", json=body).json()["eligibility"]["blocking_reasons"]


def test_statement_embedded_status_requires_only_statement_scope(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    body = golden(client)
    body["statements"] = json.loads(FIXTURE.read_text(encoding="utf-8"))["source_statements"]
    for statement, repayment in zip(body["statements"], body["repayment_history"]):
        statement["repayment_status"] = {"status": repayment["repayment_status"],
            "delinquency_severity": repayment["delinquency_severity"], "source_code": repayment["source_code"]}
    body["repayment_history"] = []
    body["consent"]["scopes"] = ["CREDIT_CARD_STATEMENTS"]
    response = client.post("/experimental/shadow-assess", json=body)
    assert response.status_code == 200
    assert response.json()["eligibility"]["eligible"] is True
    assert response.json()["scorecard"]["raw_pd"] == pytest.approx(.802589175756118, abs=1e-12)


def test_explicit_debug_endpoint_exposes_reconstructable_trace_only_when_requested(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    body = golden(client)
    normal = client.post("/experimental/shadow-assess", json=body).json()
    assert "trace" not in normal
    debug = client.post("/experimental/shadow-assess/debug", json=body).json()
    assert debug["trace_id"] == normal["trace_id"]
    assert debug["trace"]["feature_trace"]["recent_delinquency_level"]["bin_id"] == 1
    assert debug["trace"]["feature_contributions"]


def test_api_consumes_the_frozen_phase2f_shadow_specification(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    debug = client.post("/experimental/shadow-assess/debug", json=golden(client)).json()
    frozen = PHASE2 / "outputs" / "phase2f" / "frozen_shadow_scorecard.json"
    source = PHASE2 / "outputs" / "phase2b6_recovery" / "recovered_final_scorecard.json"
    assert debug["trace"]["artifact_sha256"] == hashlib.sha256(frozen.read_bytes()).hexdigest().upper()
    spec = json.loads(frozen.read_text(encoding="utf-8"))
    assert spec["artifact_provenance"]["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest().upper()


def test_caller_supplied_feature_vector_is_not_accepted(monkeypatch):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    body = golden(client)
    body["features"] = {"recent_delinquency_level": 3}
    response = client.post("/experimental/shadow-assess", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize("case", [
    "statement_only", "missing_month", "duplicate_month", "missing_status", "missing_balance",
    "missing_payment", "consent_missing", "consent_withdrawn", "wrong_consent_scope",
    "account_mismatch", "low_link_confidence", "conflicting_status", "unsupported_product",
    "multiple_accounts", "zero_denominator", "invalid_numeric", "future_record", "incomplete_provenance",
    "invalid_consent_timezone",
])
def test_all_phase2e_negative_cases_return_no_score(monkeypatch, case):
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    client = make_client()
    body = golden(client)
    if case in {"statement_only", "missing_status"}:
        body["repayment_history"] = []
    elif case == "missing_month": body["statements"] = body["statements"][:-1]
    elif case == "duplicate_month": body["statements"][-1]["statement_month"] = "2026-05"
    elif case == "missing_balance": body["statements"][0].pop("statement_balance")
    elif case == "missing_payment": body["statements"][0].pop("payment_amount")
    elif case == "consent_missing": body["consent"] = None
    elif case == "consent_withdrawn": body["consent"]["state"] = "WITHDRAWN"
    elif case == "wrong_consent_scope": body["consent"]["scopes"] = ["CREDIT_CARD_STATEMENTS"]
    elif case == "account_mismatch": body["repayment_history"][0]["account_reference"] = "other-card"
    elif case == "low_link_confidence":
        for row in body["repayment_history"]: row["source_metadata"]["account_link_confidence"] = .90
    elif case == "conflicting_status":
        body["statements"][0]["repayment_status"] = {"status": "CURRENT", "delinquency_severity": 0}
        body["repayment_history"][0]["repayment_status"] = "DELINQUENT"
        body["repayment_history"][0]["delinquency_severity"] = 1
    elif case == "unsupported_product":
        for row in body["statements"]: row["product_type"] = "PERSONAL_LOAN"
        for row in body["repayment_history"]: row["product_type"] = "PERSONAL_LOAN"
    elif case == "multiple_accounts": body["borrower_account_count"] = 2
    elif case == "zero_denominator":
        for row in body["statements"]: row["statement_balance"] = "0"
    elif case == "invalid_numeric": body["statements"][0]["statement_balance"] = "not-money"
    elif case == "future_record": body["statements"][-1]["statement_month"] = "2026-07"
    elif case == "incomplete_provenance": body["statements"][0].pop("source_metadata")
    elif case == "invalid_consent_timezone": body["consent"]["granted_at"] = "2026-01-01T00:00:00"
    response = client.post("/experimental/shadow-assess", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "INSUFFICIENT_EXPERIMENTAL_EVIDENCE"
    assert data["eligibility"]["eligible"] is False
    assert data["scorecard"] is None and data["features"] is None
    assert data["reason_codes"] == []
    assert data["eligibility"]["blocking_reasons"]


def test_no_model_fit_production_scorer_call_or_calibration_in_shadow_route():
    source = (PHASE2 / "shadow_api" / "routes.py").read_text(encoding="utf-8")
    scorer = (PHASE2 / "shadow_scorecard" / "scorer.py").read_text(encoding="utf-8")
    assert ".fit(" not in source and ".fit(" not in scorer
    assert "scoring.risk_scorer" not in source
    assert "calibration_applied" in scorer


def test_main_mounts_shadow_router_and_legacy_upload_cannot_publish_its_score():
    root = PHASE2.parents[1]
    main_source = (root / "backend" / "main.py").read_text(encoding="utf-8")
    assert "app.include_router(experimental_shadow_router)" in main_source
    assert "app.include_router(router)" in main_source
    before = json.loads((PHASE2 / "outputs" / "phase2g" / "protected_hashes_before.json").read_text())
    scorecard = PHASE2 / "outputs" / "phase2f" / "frozen_shadow_scorecard.json"
    expected = next(x["sha256"] for x in before if x["relative_path"] == "backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json")
    assert hashlib.sha256(scorecard.read_bytes()).hexdigest().upper() == expected
    result = mark_as_pending_frozen_scorecard({"status": "SCORED", "display_score": 710,
        "pd": .1, "risk_tier": "Low Risk", "fraud_risk": {"status": "clear"}})
    assert result["status"] == "INSUFFICIENT_EXPERIMENTAL_EVIDENCE"
    assert result["scoreable"] is False
    assert result["display_score"] is None and result["pd"] is None
    assert result["risk_tier"] is None and result["fraud_risk"] == {"status": "clear"}


def test_phase2e_golden_source_is_the_existing_frozen_fixture():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["fixture_id"] == "phase2e-golden-card-001"
    assert len(fixture["source_statements"]) == 6
    assert len(fixture["source_repayment_history"]) == 6


def test_mounted_application_flag_toggle_does_not_change_assess_contract(monkeypatch):
    """Import the real app while stubbing only absent OCR/model runtime dependencies.

    /assess is deliberately sent an invalid empty request, so production inference
    is never invoked. The test compares its exact response with shadow flag off/on.
    """
    import sys
    import types
    import joblib

    fake_tesseract = types.ModuleType("pytesseract")
    fake_tesseract.pytesseract = types.SimpleNamespace(tesseract_cmd=None)
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tesseract)

    class ImportOnlyModel:
        feature_names_in_ = ["credit_debit_ratio", "cashflow_cv", "net_to_gross_ratio", "utility_stability", "min_balance"]
        coef_ = [[0.0] * 5]

    monkeypatch.setattr(joblib, "load", lambda path: ImportOnlyModel() if "lr_model" in str(path)
                        else {name: object() for name in ImportOnlyModel.feature_names_in_})
    import main
    actual_client = TestClient(main.app)
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "false")
    off = actual_client.get("/experimental/shadow-golden-request")
    assess_off = actual_client.post("/assess")
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    on = actual_client.get("/experimental/shadow-golden-request")
    assess_on = actual_client.post("/assess")
    assert off.status_code == 404 and off.json()["detail"]["code"] == "EXPERIMENTAL_FEATURE_DISABLED"
    assert on.status_code == 200
    assert assess_off.status_code == assess_on.status_code == 422
    assert assess_off.json() == assess_on.json()
    assert "/assess" in main.app.openapi()["paths"]
