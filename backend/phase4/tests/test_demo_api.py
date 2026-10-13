"""Endpoint-handler integration tests; no network sockets or external services."""
from io import BytesIO
import json
import uuid

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from phase4 import demo_api as api


def setup_demo(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_PHASE4_DEMO", "true")
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    monkeypatch.setenv("PHASE4_DEMO_TOKEN", "demo-test-token")
    monkeypatch.setenv("PHASE4_DEMO_DB_PATH", str(tmp_path / "cases.sqlite3"))


def create_app(app_id, borrower):
    return api.ApplicationCreate(application_id=app_id, borrower_reference=borrower,
        requested_loan_amount=125000, loan_purpose="Demonstration", employment_category="SALARIED",
        declared_monthly_income=65000, contact_reference="SYN_CONTACT_01")


def consent(app_id, grant=True):
    return api.record_consent(app_id, api.ConsentUpdate(grant=grant,
        scopes=["CREDIT_CARD_STATEMENTS", "BUREAU_REPAYMENT_HISTORY"] if grant else []))


def packaged_evidence(scenario="healthy_repayment"):
    data=json.loads((api.Path(__file__).resolve().parents[1] / "outputs" / "demo_scenarios.json").read_text(encoding="utf-8"))
    return next(x["evidence_upload"] for x in data["scenarios"] if x["id"]==scenario)


def upload(app_id, evidence):
    raw=json.dumps(evidence).encode()
    return api.submit_evidence(app_id, UploadFile(filename="case.json", file=BytesIO(raw), headers={"content-type":"application/json"}))


def test_borrower_to_lender_path_scores_and_persists(monkeypatch,tmp_path):
    setup_demo(monkeypatch,tmp_path)
    app_id="APP_"+uuid.uuid4().hex[:8]; borrower="SYN_"+uuid.uuid4().hex[:8]
    assert api.create_application(create_app(app_id,borrower))["idempotent_replay"] is False
    assert api.create_application(create_app(app_id,borrower))["idempotent_replay"] is True
    assert consent(app_id)["state"]=="GRANTED"
    evidence=packaged_evidence(); evidence["borrower_reference"]=borrower
    stored=upload(app_id,evidence)
    assert stored["status"]=="EVIDENCE_STORED" and len(stored["sha256"])==64 and stored["synthetic_demo"] is True
    assessed=api.assess_application(app_id); result=assessed["result"]
    assert result["eligibility"]["eligible"] and result["scorecard"]["score_label"]=="PRISM Experimental Score"
    assert result["trace"]["feature_contributions"] and result["fraud_risk"]
    detail=api.get_application(app_id)["application"]
    assert len(detail["assessments"])==1
    assert detail["assessments"][0]["result"]["scorecard"]==result["scorecard"]
    assert api.list_applications()["applications"][0]["application_id"]==app_id
    assert api.delete_application(app_id)["deleted"] is True
    with pytest.raises(HTTPException) as deleted:
        api.get_application(app_id)
    assert deleted.value.status_code==404


def test_consent_required_for_upload_and_withdrawal_blocks_scoring(monkeypatch,tmp_path):
    setup_demo(monkeypatch,tmp_path); app_id="APP_"+uuid.uuid4().hex[:8]; borrower="SYN_"+uuid.uuid4().hex[:8]
    api.create_application(create_app(app_id,borrower))
    with pytest.raises(HTTPException) as no_consent:
        upload(app_id,packaged_evidence())
    assert no_consent.value.status_code==403
    consent(app_id); evidence=packaged_evidence(); evidence["borrower_reference"]=borrower; upload(app_id,evidence)
    consent(app_id,grant=False)
    with pytest.raises(HTTPException) as withdrawn:
        api.assess_application(app_id)
    assert withdrawn.value.status_code==403 and withdrawn.value.detail["code"]=="CONSENT_REQUIRED"


def test_bank_statement_only_is_persisted_without_score(monkeypatch,tmp_path):
    setup_demo(monkeypatch,tmp_path);app_id="APP_"+uuid.uuid4().hex[:8];borrower="SYN_"+uuid.uuid4().hex[:8]
    api.create_application(create_app(app_id,borrower));consent(app_id)
    bank={"evidence_type":"BANK_STATEMENT","borrower_reference":borrower,"prediction_cutoff_month":"2026-10","statements":[],"repayment_history":[]}
    upload(app_id,bank)
    result=api.assess_application(app_id)["result"]
    assert result["status"]=="INSUFFICIENT_CREDIT_ACCOUNT_EVIDENCE" and result["scorecard"] is None
    assert api.get_application(app_id)["application"]["assessments"][0]["status"]==result["status"]


def test_fraud_duplicate_identity_is_separate_from_credit_score(monkeypatch,tmp_path):
    setup_demo(monkeypatch,tmp_path); borrower="SYN_DUP_"+uuid.uuid4().hex[:8]
    outputs=[]
    for _ in range(2):
        app_id="APP_"+uuid.uuid4().hex[:8]
        api.create_application(create_app(app_id,borrower));consent(app_id)
        evidence=packaged_evidence();evidence["borrower_reference"]=borrower;upload(app_id,evidence)
        outputs.append(api.assess_application(app_id)["result"])
    assert outputs[0]["scorecard"]["raw_pd"]==outputs[1]["scorecard"]["raw_pd"]
    assert any(flag["rule"]=="DUPLICATE_IDENTITY" for flag in outputs[1]["fraud_risk"]["flags"])


def test_auth_scope_borrower_link_and_readiness(monkeypatch,tmp_path):
    setup_demo(monkeypatch,tmp_path)
    with pytest.raises(HTTPException) as disabled:
        api._authorize("Bearer wrong")
    # _authorize reads configured token and is invoked directly with the header value.
    assert disabled.value.status_code==401
    app_id="APP_"+uuid.uuid4().hex[:8];api.create_application(create_app(app_id,"SYN_MATCH"))
    with pytest.raises(HTTPException) as missing_scope:
        api.record_consent(app_id,api.ConsentUpdate(grant=True,scopes=["CREDIT_CARD_STATEMENTS"]))
    assert missing_scope.value.status_code==422
    consent(app_id)
    mismatched=packaged_evidence()
    with pytest.raises(HTTPException) as mismatch:
        upload(app_id,mismatched)
    assert mismatch.value.status_code==409
    modified=packaged_evidence();modified["borrower_reference"]="SYN_MATCH";modified["statements"][0]["statement_balance"] = str(float(modified["statements"][0]["statement_balance"])+1)
    assert api._is_packaged_synthetic(api.CreditEvidenceUpload.model_validate(modified)) is False
    monkeypatch.setenv("PHASE4_DEMO_DB_PATH",str(tmp_path/"ready.sqlite3"))
    ok,detail=api.readiness()
    assert ok and detail["scorecard"]=="loaded_and_verified" and detail["database"]=="connected"
