from types import SimpleNamespace

from route.lender_routes import _application_summary


def test_legacy_score_does_not_appear_as_a_frozen_lender_assessment():
    application = SimpleNamespace(application_id=17, application_date=None,
                                  application_status="INSUFFICIENT_EVIDENCE")
    user = SimpleNamespace(phone="synthetic-borrower")
    legacy_score = SimpleNamespace(credit_score=645, probability_default=0.22,
                                   risk_tier="medium", model_name="WoE_Logistic_Scorecard",
                                   score_status="ACTIVE")

    result = _application_summary(application, user, legacy_score, 2)

    assert result["risk_score"] is None
    assert result["probability_of_default"] is None
    assert result["risk_tier"] is None
    assert result["assessment_status"] == "INSUFFICIENT_EVIDENCE"


def test_only_frozen_shadow_rows_are_lender_score_candidates():
    application = SimpleNamespace(application_id=18, application_date=None,
                                  application_status="ASSESSED_EXPERIMENTAL")
    user = SimpleNamespace(phone="synthetic-borrower")
    frozen_score = SimpleNamespace(credit_score=282, probability_default=0.8026,
                                   risk_tier=None, model_name="PRISM_PHASE2F_FROZEN",
                                   score_status="EXPERIMENTAL_SHADOW_SCORE")

    result = _application_summary(application, user, frozen_score, 6)

    assert result["risk_score"] == 282
    assert result["probability_of_default"] == 0.8026
    assert result["risk_tier"] is None
    assert result["assessment_status"] == "SCORED"
