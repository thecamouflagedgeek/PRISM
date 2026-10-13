"""PostgreSQL-backed verification using only synthetic borrower/application rows."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import uuid

import fitz
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.session_store import create_session
from database.db import engine, get_db
from database.models import Application, Consent, Document, ExperimentalAssessment, User
from ingestion.document_pipeline import DocumentPipeline
from main import app
from phase2.credit_parser.document_extraction import (
    classify_card_statement, extract_document_text, extract_labeled_fields,
)
from services.ocr_service import get_ocr_engine


BACKEND = Path(__file__).resolve().parent
FIXTURES = BACKEND / "phase2" / "outputs" / "synthetic_statement_fixtures"
GROUND_TRUTH = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))


@pytest.fixture
def postgres_demo(tmp_path, monkeypatch):
    """All DB writes run inside a rollback-only outer transaction."""
    monkeypatch.setenv("PRISM_DOCUMENT_STORAGE_ROOT", str(tmp_path / "documents"))
    # Exercise the intentionally gated Phase 2 shadow simulator in this test only.
    monkeypatch.setenv("ENABLE_EXPERIMENTAL_SHADOW_SCORING", "true")
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    phone = f"+1999{uuid.uuid4().int % 10**10:010d}"
    user = User(phone=phone, created_at=datetime.utcnow())
    db.add(user); db.flush()
    application = Application(user_id=user.user_id, application_date=datetime(2026, 10, 1), application_status="IN_PROGRESS")
    db.add(application); db.flush()
    db.add(Consent(application_id=application.application_id, bank_consent=False,
        salary_consent=False, utility_consent=False, dpdpa_consent=True,
        consent_version="synthetic-test", consent_timestamp=datetime.utcnow()))
    db.commit()
    borrower = create_session(phone, user_id=user.user_id, application_id=application.application_id, role="borrower")
    lender = create_session("synthetic-lender", user_id=None, application_id=None, role="lender")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield {"client": TestClient(app), "db": db, "user": user, "application": application,
            "borrower": borrower, "lender": lender}
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        outer.rollback()
        connection.close()


def statement_paths(profile):
    return [FIXTURES / f"{profile}_{month}.pdf" for month in ("2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09")]


def multipart(paths):
    return [("statement_files", (path.name, path.read_bytes(), "application/pdf")) for path in paths]


def test_document_extraction_digital_scanned_pdf_and_image_and_classifier():
    ocr = get_ocr_engine()
    samples = [FIXTURES / "consistent_2026-09.pdf",
        FIXTURES / "repeated_2026-09_scanned.pdf", FIXTURES / "repeated_2026-09_scanned.png"]
    methods = []
    for path in samples:
        text, method, confidence, pages = extract_document_text(str(path), ocr)
        classified, reason = classify_card_statement(text)
        fields, gaps = extract_labeled_fields(text)
        assert classified, reason
        assert 'PAYMENT_DUE_DATE_NOT_AFTER_STATEMENT_DATE' in gaps
        assert not any(gap.startswith('MISSING_FIELD:') for gap in gaps)
        assert fields["statement_month"] == "2026-09"
        assert fields["status"] in {"CURRENT", "DELINQUENT"}
        if method == "native_pdf_text":
            assert confidence == 0.0  # Field coverage is measured by the adapter.
        else:
            assert confidence >= .90
        assert pages == 1
        methods.append(method)
    assert methods == ["native_pdf_text", "tesseract_scanned_page_ocr", "tesseract_image_ocr"]

    bank = "BANK STATEMENT\nIFSC IFSC\nUPI debit credit\nCredit card payment transaction\nAmount Due"
    assert classify_card_statement(bank) == (False, "BANK_STATEMENT_OR_AMBIGUOUS_CLASSIFICATION")


def test_six_document_upload_scores_persists_refresh_lender_whatif_and_pdf(postgres_demo):
    state = postgres_demo
    validated = BACKEND.parent / 'tests/fixtures/prism_demo_validated'
    target = {'feature_vector': json.loads((validated / 'ground_truth.json').read_text())['frozen_model_input_candidates'],
        'pd': .2727810906249319, 'uncapped_score': 454.635898966963}
    paths = sorted(validated.glob('Credit_Card_*.pdf'))
    response = state["client"].post("/assess/credit-card-statements",
        headers={"session-id": state["borrower"].session_id},
        data={"credit_card_consent": "true", "prediction_cutoff_month": "2026-09"}, files=multipart(paths))
    assert response.status_code == 200, response.text
    assessment = response.json()
    assert assessment["assessment_status"] == "SCORED"
    assert assessment["decision_use"] == "NOT_FOR_CREDIT_DECISION"
    assert assessment["assessment_id"]
    assert set(assessment["feature_values"]) == set(target["feature_vector"])
    for feature, expected in target["feature_vector"].items():
        assert float(assessment["feature_values"][feature]) == pytest.approx(float(expected), abs=1e-12)
    assert assessment["probability_of_default"] == pytest.approx(target["pd"], abs=1e-12)
    assert assessment["score"] == pytest.approx(target["uncapped_score"], abs=1e-10)
    assert len(assessment["source_document_ids"]) == 6
    assert all(item["document_type"] == "CREDIT_CARD_STATEMENT" for item in assessment["document_findings"]["documents"])

    row = state["db"].query(ExperimentalAssessment).filter_by(assessment_id=assessment["assessment_id"]).one()
    assert row.application_id == state["application"].application_id
    assert row.user_id == state["user"].user_id
    assert row.model_version == assessment["model_version"]
    assert float(row.score) == pytest.approx(target["uncapped_score"], abs=1e-10)

    repeat = state["client"].post("/assess/credit-card-statements",
        headers={"session-id": state["borrower"].session_id},
        data={"credit_card_consent": "true", "prediction_cutoff_month": "2026-09"}, files=multipart(paths))
    assert repeat.status_code == 200
    assert repeat.json()["assessment_id"] == assessment["assessment_id"]
    assert repeat.json()["idempotent_replay"] is True
    assert state["db"].query(ExperimentalAssessment).filter_by(application_id=state["application"].application_id).count() == 1

    refreshed = state["client"].get(f"/assess/credit-card-assessments/{assessment['assessment_id']}",
        headers={"session-id": state["borrower"].session_id})
    assert refreshed.status_code == 200
    assert refreshed.json()["score"] == assessment["score"]
    assert refreshed.json()["assessment_id"] == assessment["assessment_id"]
    latest = state["client"].get("/assess/credit-card-assessments/latest",
        headers={"session-id": state["borrower"].session_id})
    assert latest.status_code == 200
    assert latest.json()["assessment_id"] == assessment["assessment_id"]

    other_phone = f"+1888{uuid.uuid4().int % 10**10:010d}"
    other_user = User(phone=other_phone, created_at=datetime.utcnow())
    state["db"].add(other_user); state["db"].flush()
    other_app = Application(user_id=other_user.user_id, application_date=datetime(2026, 10, 1),
        application_status="IN_PROGRESS")
    state["db"].add(other_app); state["db"].flush()
    state["db"].add(Consent(application_id=other_app.application_id, bank_consent=False,
        salary_consent=False, utility_consent=False, dpdpa_consent=True,
        consent_version="synthetic-test", consent_timestamp=datetime.utcnow()))
    state["db"].commit()
    other_borrower = create_session(other_phone, user_id=other_user.user_id,
        application_id=other_app.application_id, role="borrower")
    cross_borrower = state["client"].get(
        f"/assess/credit-card-assessments/{assessment['assessment_id']}",
        headers={"session-id": other_borrower.session_id})
    assert cross_borrower.status_code == 404

    lender_detail = state["client"].get(f"/lender/applications/{state['application'].application_id}",
        headers={"session-id": state["lender"].session_id})
    assert lender_detail.status_code == 200
    lender_result = lender_detail.json()["experimental_assessment"]
    assert lender_result["assessment_id"] == assessment["assessment_id"]
    assert lender_result["score"] == assessment["score"]
    assert lender_result["probability_of_default"] == assessment["probability_of_default"]
    assert lender_result["reason_codes"] == assessment["reason_codes"]

    scenario = dict(assessment["feature_values"])
    scenario["payment_to_statement_ratio"] = .90
    simulated = state["client"].post(f"/assess/credit-card-assessments/{assessment['assessment_id']}/what-if",
        headers={"session-id": state["borrower"].session_id}, json=scenario)
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["persisted"] is False
    assert state["db"].query(ExperimentalAssessment).filter_by(application_id=state["application"].application_id).count() == 1
    assert state["db"].query(ExperimentalAssessment).filter_by(assessment_id=assessment["assessment_id"]).one().score == row.score

    report = state["client"].get(f"/assess/credit-card-assessments/{assessment['assessment_id']}/report.pdf",
        headers={"session-id": state["borrower"].session_id})
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    pdf = fitz.open(stream=report.content, filetype="pdf")
    report_text = "\n".join(page.get_text() for page in pdf)
    assert assessment["assessment_id"] in report_text
    assert f"{assessment['score']:.12f}" in report_text
    assert f"{assessment['probability_of_default']:.16f}" in report_text


def test_insufficient_and_authorization_are_fail_closed(postgres_demo):
    state = postgres_demo
    bank = fitz.open(); page = bank.new_page(); page.insert_text((48, 48),
        "BANK STATEMENT\nIFSC IFSC\nUPI NEFT RTGS\nCredit card payment transaction")
    bank_bytes = bank.tobytes(); bank.close()
    result = state["client"].post("/assess/credit-card-statements",
        headers={"session-id": state["borrower"].session_id}, data={"credit_card_consent": "true"},
        files=[("statement_files", ("bank.pdf", bank_bytes, "application/pdf"))])
    assert result.status_code == 200, result.text
    assert result.json()["assessment_status"] == "INSUFFICIENT_EVIDENCE"
    assert result.json()["score"] is None and result.json()["probability_of_default"] is None

    borrower_not_lender = state["client"].get(f"/lender/applications/{state['application'].application_id}",
        headers={"session-id": state["borrower"].session_id})
    assert borrower_not_lender.status_code == 403
    no_session = state["client"].get(f"/lender/applications/{state['application'].application_id}")
    assert no_session.status_code == 401
