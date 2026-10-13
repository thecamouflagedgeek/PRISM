"""Authenticated borrower workflow for extracted experimental card assessments."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import textwrap
import logging
from uuid import uuid4

import fitz
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from core.session_store import get_session
from core.demo_receipt import record_demo_receipt
from database.db import get_db
from database.models import (Application, Consent as DbConsent, Document,
    ExperimentalAssessment, User, AuditEvent)
from ingestion.document_pipeline import DocumentPipeline
from phase2.credit_parser.document_extraction import (
    classify_card_statement, extract_document_text, extract_labeled_fields,
)
from phase2.credit_parser.normalizer import run_equivalence_path
from phase2.credit_evidence.models import Consent, ConsentState
from phase2.shadow_scorecard.artifacts import load_scorecard, FEATURE_ORDER
from phase2.shadow_scorecard.scorer import score_validated_result, ShadowScoreError


router = APIRouter(prefix="/assess", tags=["Experimental Credit Account Assessment"])
MODEL_NAME = "PRISM_PHASE2F_FROZEN"
MODEL_PATH = Path(__file__).resolve().parents[1] / "phase2" / "outputs" / "phase2f" / "frozen_shadow_scorecard.json"
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_FILES = 12


def _jsonable(value):
    from dataclasses import asdict, is_dataclass
    from enum import Enum
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _session_owner(session_id: str, db: Session):
    session = get_session(session_id)
    if not session or not session.is_authenticated:
        raise HTTPException(401, "Authenticated borrower session required")
    if getattr(session, "role", "borrower") != "borrower" or not session.user_id or not session.application_id:
        raise HTTPException(403, "An active borrower application is required")
    app = db.query(Application).filter(Application.application_id == session.application_id).first()
    if app is None or app.user_id != session.user_id:
        raise HTTPException(403, "Borrower session is not authorized for this application")
    consent = db.query(DbConsent).filter(DbConsent.application_id == app.application_id).first()
    if not consent or not consent.dpdpa_consent:
        raise HTTPException(403, "Recorded personal-data processing consent is required")
    return session, app


def _assessment_payload(row: ExperimentalAssessment) -> dict:
    score = float(row.score) if row.score is not None else None
    pd = float(row.probability_default) if row.probability_default is not None else None
    status = "EXPERIMENTAL_SHADOW_SCORE" if row.assessment_status == "SCORED" else "INSUFFICIENT_EXPERIMENTAL_EVIDENCE"
    findings = row.document_findings or {}
    output = {
        "status": status, "assessment_status": row.assessment_status,
        "assessment_type": "CREDIT_ACCOUNT_EXPERIMENTAL",
        "decision_use": "NOT_FOR_CREDIT_DECISION", "assessment_id": row.assessment_id,
        "trace_id": row.assessment_id, "application_id": row.application_id,
        "user_id": row.user_id, "model_version": row.model_version,
        "artifact_sha256": row.model_version, "model_status": "PHASE_2B6_INCONCLUSIVE",
        "assessment_timestamp": row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        "score": score, "probability_of_default": pd, "risk_tier": None,
        "feature_coverage": 1.0 if row.assessment_status == "SCORED" else 0.0,
        "feature_values": row.feature_values, "features": row.feature_values,
        "woe_values": row.woe_values, "feature_contributions": row.feature_contributions,
        "feature_trace": findings.get("feature_trace"),
        "reason_codes": row.reason_codes or [], "improvement_recommendations": row.recommendations or [],
        "document_findings": findings, "evidence_validation": row.evidence_validation,
        "source_document_ids": row.source_document_ids, "consent_record": row.consent_record,
        "limitations": ["NOT_EXTERNALLY_VALIDATED", "NOT_CURRENT_MARKET_VALIDATED",
            "NOT_INDIAN_MARKET_VALIDATED", "NOT_PRODUCTION_APPROVED"],
    }
    if row.assessment_status == "SCORED":
        output["scorecard"] = {
            "experimental_shadow_score": score, "raw_pd": pd,
            "logit": float(row.logit), "score_label": "Experimental Shadow Score",
            "pdo_presentation_only": True,
        }
    else:
        output.update({"scorecard": None, "data_sufficiency": {
            "reasons": (row.evidence_validation or {}).get("blocking_reasons", []),
            "message": "The uploaded statements did not establish all four features under the frozen evidence rules.",
        }})
    return output


def _persist(db, *, session, app, cutoff, doc_rows, payload, model_version, score_result=None):
    input_identity = {
        "application_id": app.application_id, "cutoff": cutoff,
        "document_hashes": sorted(d.document_hash for d in doc_rows),
        "parser_version": "explicit-card-labels-v4-dates",
        "model_version": model_version, "consent_scope": "CREDIT_CARD_STATEMENTS",
    }
    input_hash = sha256(json.dumps(input_identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = db.query(ExperimentalAssessment).filter_by(
        application_id=app.application_id, input_sha256=input_hash).first()
    if existing:
        return existing, True

    now = datetime.utcnow()
    status = "SCORED" if score_result else "INSUFFICIENT_EVIDENCE"
    features = score_result.get("feature_values") if score_result else None
    woe = score_result.get("woe_values") if score_result else None
    contributions = score_result.get("feature_contributions") if score_result else None
    findings = dict(payload.get("document_findings") or {})
    findings['processing_trace'] = ['UPLOAD_RECEIVED','DOCUMENT_CLASSIFIED','PDF_EXTRACTED','FIELDS_PARSED','EVIDENCE_AGGREGATED'] + (
        ['VALIDATION_PASSED','FEATURES_COMPUTED','SCORE_COMPUTED','ASSESSMENT_PERSISTED'] if score_result else ['VALIDATION_FAILED','ASSESSMENT_PERSISTED'])
    for finding in findings.get('documents', []):
        finding['validation_result'] = 'VALID' if score_result else 'NOT_ELIGIBLE'
        finding['rejection_reasons'] = finding.get('findings', []) or ([] if score_result else payload.get('evidence_validation', {}).get('blocking_reasons', []))
    if score_result:
        findings["feature_trace"] = _jsonable(score_result.get("feature_trace", {}))
    row = ExperimentalAssessment(
        assessment_id=str(uuid4()), application_id=app.application_id, user_id=session.user_id,
        input_sha256=input_hash, model_name=MODEL_NAME, model_version=model_version,
        assessment_status=status, prediction_cutoff_month=cutoff,
        feature_values=_jsonable(features), woe_values=_jsonable(woe),
        feature_contributions=_jsonable(contributions),
        logit=score_result.get("logit") if score_result else None,
        probability_default=score_result.get("pd") if score_result else None,
        score=score_result.get("score") if score_result else None,
        reason_codes=_jsonable(score_result.get("reason_codes", [])) if score_result else [],
        recommendations=_jsonable(payload.get("improvement_recommendations", [])) if score_result else [],
        source_document_ids=[d.document_id for d in doc_rows],
        evidence_validation=_jsonable(payload.get("evidence_validation", {})),
        document_findings=_jsonable(findings),
        consent_record=_jsonable(payload.get("consent_record", {})), created_at=now,
    )
    try:
        db.add(row)
        db.add(AuditEvent(application_id=app.application_id, action="experimental_assessment_created",
            entity="experimental_assessment", status="scored" if score_result else "insufficient",
            event_timestamp=now,
            details={"assessment_id": row.assessment_id, "model_version": model_version,
                "source_document_count": len(doc_rows), "input_sha256": input_hash}))
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        existing = db.query(ExperimentalAssessment).filter_by(
            application_id=app.application_id, input_sha256=input_hash).first()
        if existing:
            return existing, True
        raise
    return row, False


def _extract_uploaded(file: UploadFile, *, session, app, db, ocr_engine):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(415, f"Unsupported statement format: {suffix or 'no extension'}")
    content = file.file.read(MAX_FILE_BYTES + 1)
    if not content or len(content) > MAX_FILE_BYTES:
        raise HTTPException(413, "Each statement must be between 1 byte and 15 MB")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(content)
        tmp.close()
        digest = sha256(content).hexdigest()
        doc = db.query(Document).filter_by(application_id=app.application_id, document_hash=digest).first()
        if doc is None:
            from database.crud import save_document
            doc = save_document(db, app.application_id, "CREDIT_CARD", file.filename or "statement" , tmp.name,
                # prism.documents.parser_version is VARCHAR(20).
                parser_version="phase2e-doc-v2")
        text, method, confidence, page_count = extract_document_text(tmp.name, ocr_engine)
        is_card, type_reason = classify_card_statement(text)
        if not is_card:
            doc.processing_status = "UNSUPPORTED"
            db.commit()
            return doc, digest, None, {"document_id": doc.document_id, "file_name": file.filename,
                "document_type": "UNKNOWN_OR_NON_CARD", "classification_reason": type_reason,
                "extraction_method": method, "extraction_confidence": confidence,
                "page_count": page_count, "findings": [type_reason]}
        fields, gaps = extract_labeled_fields(text)
        required_field_count = 9
        field_coverage = sum(k in fields for k in ('statement_month','account_reference','provider','masked_account_number','currency','statement_balance','payment_amount','status','delinquency_severity')) / required_field_count
        # For native text, use the observed fraction of required explicit fields;
        # for OCR, require both field coverage and measured token confidence.
        quality_score = field_coverage if method == "native_pdf_text" else min(float(confidence or 0.0), field_coverage)
        quality_basis = "required_explicit_field_coverage" if method == "native_pdf_text" else "min_ocr_token_confidence_and_required_field_coverage"
        meta = {
            "source_document_id": str(doc.document_id), "extraction_method": method,
            "extraction_confidence": max(0.0, min(1.0, quality_score)),
            "extraction_quality_basis": quality_basis,
            "required_field_coverage": field_coverage,
            "account_link_confidence": 0.0, "authenticated": True,
            "page_or_record_id": "page:1" if page_count == 1 else f"document:{doc.document_id}:pages:1-{page_count}",
            "field_provenance": fields.get("_field_provenance", {}),
        }
        payload = {k: v for k, v in fields.items() if not k.startswith("_")}
        if "status" in payload:
            payload["repayment_status"] = {"status": payload.pop("status"),
                "delinquency_severity": payload.pop("delinquency_severity", None)}
        for key in ("statement_balance", "payment_amount"):
            if key in payload:
                import re
                payload[key] = re.sub(r"^(?:INR|USD|EUR|GBP)\s+", "", payload[key], flags=re.I)
        payload["product_type"] = "CREDIT_CARD"
        payload["source_metadata"] = meta
        doc.processing_status = "EXTRACTED" if not gaps else "PARTIALLY_EXTRACTED"
        db.commit()
        return doc, digest, {"text": text, "source_metadata": meta, "payload": payload}, {
            "document_id": doc.document_id, "file_name": file.filename,
            "document_type": "CREDIT_CARD_STATEMENT", "classification_reason": type_reason,
            "extraction_method": method, "extraction_confidence": confidence,
            "extraction_quality_basis": quality_basis,
            "required_field_coverage": field_coverage,
            "page_count": page_count, "fields": {k: v for k, v in payload.items() if k not in {"source_metadata"}},
            "declared_page_count": max([int(total) for _, total in __import__('re').findall(r'\bPage\s+(\d+)\s+of\s+(\d+)', text, __import__('re').I)] or [0]) or None,
            "processing_trace": ['UPLOAD_RECEIVED','DOCUMENT_CLASSIFIED','PDF_EXTRACTED','FIELDS_PARSED'],
            "source_lines": fields.get("_line_numbers", {}),
            "field_provenance": fields.get("_field_provenance", {}),
            "auxiliary_fields": fields.get("_auxiliary_fields", {}),
            "auxiliary_source_lines": fields.get("_auxiliary_line_numbers", {}),
            "findings": gaps,
        }
    except (ValueError, RuntimeError, fitz.FileDataError) as exc:
        db.rollback()
        raise HTTPException(422, "Unreadable, corrupted, or encrypted card statement. Upload a readable unlocked PDF.") from exc
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.post("/credit-card-statements")
async def assess_credit_card_statements(
    statement_files: list[UploadFile] = File(...),
    credit_card_consent: bool = Form(...),
    prediction_cutoff_month: str | None = Form(None),
    session_id: str = Header(...),
    ocr_engine=Depends(lambda: __import__("services.ocr_service", fromlist=["get_ocr_engine"]).get_ocr_engine()),
    db: Session = Depends(get_db),
):
    if not statement_files or len(statement_files) > MAX_FILES:
        raise HTTPException(422, f"Upload between 1 and {MAX_FILES} card statements")
    if not credit_card_consent:
        raise HTTPException(403, "Credit-card statement processing consent is required")
    session, app = _session_owner(session_id, db)
    cutoff = app.application_date.strftime("%Y-%m")
    request_id = str(uuid4())
    record_demo_receipt(app.application_id, '/assess/credit-card-statements', {'statement_files': statement_files}, prediction_cutoff_month)
    logging.getLogger('uvicorn.error').info(
        "assessment request_id=%s application_id=%s type=CREDIT_ACCOUNT_EXPERIMENTAL files=%s category=CARD stage=received",
        request_id, app.application_id, len(statement_files))
    if prediction_cutoff_month is not None:
        from phase2.credit_parser.parser import normalize_month
        try:
            requested = normalize_month(prediction_cutoff_month)
        except ValueError as exc:
            raise HTTPException(422, "Assessment cutoff must be YYYY-MM") from exc
        if requested > cutoff:
            raise HTTPException(422, "Assessment cutoff cannot be after the application month")
        cutoff = requested
    docs, digests, structured, document_findings = [], [], [], []
    for file in statement_files:
        doc, digest, extracted, finding = _extract_uploaded(file, session=session, app=app, db=db, ocr_engine=ocr_engine)
        docs.append(doc); digests.append(digest); document_findings.append(finding)
        if extracted:
            structured.append(extracted)
    artifact = load_scorecard(MODEL_PATH)
    payload = {
        "document_findings": {"documents": document_findings, "prediction_cutoff_month": cutoff,
            "assessment_timing": "HISTORICAL_SNAPSHOT" if cutoff < app.application_date.strftime("%Y-%m") else "APPLICATION_MONTH",
            "window_months": 6, "model_status": "PHASE_2B6_INCONCLUSIVE"},
        "consent_record": {"state": "GRANTED", "scope": "CREDIT_CARD_STATEMENTS",
            "granted_by_user_id": session.user_id, "granted_at": datetime.now(timezone.utc).isoformat(),
            "consent_version": "credit-card-experimental-v1"},
    }
    score_result = None
    blockers = []
    blockers.extend(reason for finding in document_findings for reason in finding.get('findings', []))
    for finding in document_findings:
        aux = finding.get('auxiliary_fields', {})
        if aux.get('declared_cutoff_month') and aux['declared_cutoff_month'] != cutoff:
            blockers.append('DECLARED_HISTORICAL_CUTOFF_MISMATCH')
        observed = aux.get('repayment_observation_date')
        if observed:
            from phase2.credit_parser.parser import normalize_month
            if normalize_month(observed) >= cutoff: blockers.append('REPAYMENT_OBSERVATION_NOT_BEFORE_CUTOFF')
    if len(structured) != len(statement_files):
        blockers.append("NON_CARD_OR_UNREADABLE_DOCUMENT")
    if structured:
        identities = {
            (item["payload"].get("account_reference"), item["payload"].get("masked_account_number"),
             item["payload"].get("provider"), item["payload"].get("currency")) for item in structured
        }
        linked = len(identities) == 1 and all(all(identity) for identity in next(iter(identities)))
        for finding in document_findings:
            finding['account_linked'] = linked
        link_confidence = 0.99 if linked else 0.0
        for item in structured:
            item["source_metadata"]["account_link_confidence"] = link_confidence
            item["payload"]["source_metadata"]["account_link_confidence"] = link_confidence
            if item["source_metadata"]["extraction_confidence"] < 0.90:
                blockers.append("LOW_EXTRACTION_CONFIDENCE")
            item["text"] = item["text"].replace("\r", "")
        consent = Consent(ConsentState.GRANTED, frozenset({"CREDIT_CARD_STATEMENTS"}),
            granted_at=datetime.now(timezone.utc), version="credit-card-experimental-v1")
        assembly = run_equivalence_path(
            [item["payload"] for item in structured], (), consent=consent, prediction_cutoff_month=cutoff,
            borrower_reference=str(session.user_id), at=datetime.now(timezone.utc), text=False,
        )
        eligibility = assembly.eligibility
        if blockers and eligibility is not None:
            from dataclasses import replace
            eligibility = replace(eligibility, eligible_for_phase2b6_scorecard=False,
                blocking_reasons=tuple(dict.fromkeys(tuple(eligibility.blocking_reasons) + tuple(blockers))))
        payload["evidence_validation"] = {
            "assembly_state": assembly.state,
            "valid": bool(assembly.validation and assembly.validation.valid and not blockers),
            "eligible": bool(eligibility and eligibility.eligible_for_phase2b6_scorecard and not blockers),
            "blocking_reasons": list(dict.fromkeys(list(eligibility.blocking_reasons if eligibility else []) + blockers)),
            "warnings": list(eligibility.warnings if eligibility else []),
            "validated_months": list(assembly.validation.months if assembly.validation else []),
            "expected_months": list(__import__("phase2.credit_evidence.validation", fromlist=["expected_months"]).expected_months(cutoff)),
            "feature_derivation": {
                "recent_delinquency_level": "explicit delinquency severity from latest statement month; 0 means explicitly current",
                "months_with_delinquency": "count of the six explicit monthly severity values greater than zero",
                "payment_to_statement_ratio": "sum of settled payment amounts applied to these statements / sum(max(statement balance, 0))",
                "mean_statement_balance": "arithmetic mean of the six account statement balances in original currency units",
            },
        }
        if eligibility and eligibility.eligible_for_phase2b6_scorecard and not blockers:
            try:
                score_result = score_validated_result(assembly, artifact=artifact)
            except ShadowScoreError as exc:
                payload["evidence_validation"]["blocking_reasons"] = list(exc.reasons)
        if assembly.features and assembly.features.values:
            payload["evidence_validation"]["candidate_feature_values"] = {
                key: str(value) for key, value in assembly.features.values.items()
            }
    else:
        payload["evidence_validation"] = {
            "valid": False, "eligible": False,
            "blocking_reasons": ["NO_RECOGNIZED_CREDIT_CARD_STATEMENT"],
            "expected_months": list(__import__("phase2.credit_evidence.validation", fromlist=["expected_months"]).expected_months(cutoff)),
        }
    if score_result:
        recs = {
            "recent_delinquency_level": "Review the documented repayment history and aim to pay future statements by their due dates.",
            "months_with_delinquency": "Build a consistent record of on-time repayments over future statement cycles.",
            "payment_to_statement_ratio": "Where affordable, pay a larger share of statement balances by the due date.",
            "mean_statement_balance": "Review outstanding balances and make repayments that fit your circumstances.",
        }
        payload["improvement_recommendations"] = [{"reason_code": row["code"], "feature": row["code"],
            "message": recs[row["code"]], "causality_claim": False} for row in score_result["reason_codes"]]
    row, replay = _persist(db, session=session, app=app, cutoff=cutoff, doc_rows=docs,
        payload=payload, model_version=artifact["artifact_sha256"], score_result=score_result)
    result = _assessment_payload(row)
    result["idempotent_replay"] = replay
    result["decision_use"] = "NOT_FOR_CREDIT_DECISION"
    result['request_id'] = request_id
    logging.getLogger('uvicorn.error').info(
        "assessment request_id=%s application_id=%s type=CREDIT_ACCOUNT_EXPERIMENTAL files=%s stage=complete outcome=%s",
        request_id, app.application_id, len(statement_files), row.assessment_status)
    return result


@router.get("/credit-card-assessments/latest")
def get_latest_borrower_assessment(session_id: str = Header(...), db: Session = Depends(get_db)):
    session, app = _session_owner(session_id, db)
    row = db.query(ExperimentalAssessment).filter_by(application_id=app.application_id, user_id=session.user_id).order_by(ExperimentalAssessment.created_at.desc()).first()
    if row is None:
        raise HTTPException(404, "No credit-card assessment exists for this application")
    return _assessment_payload(row)


@router.get("/credit-card-assessments/{assessment_id}")
def get_borrower_assessment(assessment_id: str, session_id: str = Header(...), db: Session = Depends(get_db)):
    session, _app = _session_owner(session_id, db)
    row = db.query(ExperimentalAssessment).filter_by(assessment_id=assessment_id, user_id=session.user_id, application_id=_app.application_id).first()
    if row is None:
        raise HTTPException(404, "Assessment not found")
    return _assessment_payload(row)


@router.post("/credit-card-assessments/{assessment_id}/what-if")
def borrower_assessment_what_if(assessment_id: str, scenario: dict,
        session_id: str = Header(...), db: Session = Depends(get_db)):
    session, _app = _session_owner(session_id, db)
    row = db.query(ExperimentalAssessment).filter_by(assessment_id=assessment_id, user_id=session.user_id,
        application_id=_app.application_id, assessment_status="SCORED").first()
    if row is None:
        raise HTTPException(404, "Scored assessment not found")
    if set(scenario) != set(FEATURE_ORDER):
        raise HTTPException(422, "Scenario must contain the four frozen scorecard features")
    from phase2.shadow_api.routes import _score_feature_vector
    from pydantic import ValidationError
    try:
        baseline = _score_feature_vector(row.feature_values)
        hypothetical = _score_feature_vector(scenario)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(422, "Invalid hypothetical feature values") from exc
    return {"status": "HYPOTHETICAL_ONLY", "assessment_id": row.assessment_id,
        "baseline": baseline, "scenario": hypothetical, "persisted": False,
        "delta": {"score": hypothetical["scorecard"]["experimental_shadow_score"] - baseline["scorecard"]["experimental_shadow_score"],
            "raw_pd": hypothetical["scorecard"]["raw_pd"] - baseline["scorecard"]["raw_pd"]}}


@router.get("/credit-card-assessments/{assessment_id}/report.pdf")
def borrower_assessment_pdf(assessment_id: str, session_id: str = Header(...), db: Session = Depends(get_db)):
    session, _app = _session_owner(session_id, db)
    row = db.query(ExperimentalAssessment).filter_by(assessment_id=assessment_id, user_id=session.user_id, application_id=_app.application_id).first()
    if row is None:
        raise HTTPException(404, "Assessment not found")
    result = _assessment_payload(row)
    document = fitz.open()
    lines = ["PRISM Experimental Credit Account Assessment", "NOT FOR CREDIT DECISIONS", "",
        f"Assessment: {row.assessment_id}", f"Application: {row.application_id}",
        f"Status: {row.assessment_status}", f"Model SHA-256: {row.model_version}",
        f"Created: {row.created_at.isoformat()}Z"]
    if row.assessment_status == "SCORED":
        lines.extend([f"Experimental score (uncapped): {float(row.score):.12f}",
            f"Raw uncalibrated PD: {float(row.probability_default):.16f}",
            "", "FOUR FROZEN MODEL FEATURES"])
        lines.extend(f"{key}: {value}" for key, value in (row.feature_values or {}).items())
        lines.extend(["", "WOE VALUES"])
        lines.extend(f"{key}: {value}" for key, value in (row.woe_values or {}).items())
        lines.extend(["", "SIGNED LOGIT CONTRIBUTIONS"])
        lines.extend(f"{key}: {value:+.12f}" for key, value in (row.feature_contributions or {}).items())
        lines.extend(["", "REASON CODES"])
        for reason in row.reason_codes or []:
            lines.append(f"{reason.get('code')}: {reason.get('explanation', reason.get('direction', ''))}; contribution {reason.get('contribution')}")
        lines.extend(["", "RECOMMENDATIONS"])
        lines.extend(item.get('message', str(item)) if isinstance(item, dict) else str(item) for item in row.recommendations or [])
    validation = row.evidence_validation or {}
    findings = result['document_findings']
    lines.extend(["", "EVIDENCE AND ASSESSMENT WINDOW",
        f"Exclusive cutoff month: {row.prediction_cutoff_month}",
        f"Timing: {findings.get('assessment_timing', 'APPLICATION_MONTH')}",
        f"Expected months: {', '.join(validation.get('expected_months', []))}",
        f"Observed months: {', '.join(validation.get('validated_months', []))}",
        f"Evidence valid: {validation.get('valid')}",
        "Evidence gaps: " + (', '.join(validation.get('blocking_reasons', [])) or 'None recorded'),
        "", "SOURCE DOCUMENT FINDINGS"])
    for item in findings.get('documents', []):
        lines.extend([f"Document {item.get('document_id')}: {item.get('file_name')}",
            f"  Type: {item.get('document_type')}; pages: {item.get('page_count')}; method: {item.get('extraction_method')}",
            f"  Required field coverage: {item.get('required_field_coverage')}; basis: {item.get('extraction_quality_basis')}",
            "  Findings: " + (', '.join(item.get('findings', [])) or 'None recorded')])
    lines.extend(["", "LIMITATIONS",
        "PHASE_2B6_INCONCLUSIVE. Taiwan-trained experimental model; not validated for Indian lending.",
        "Not externally/current-market validated; not production approved. Not a CIBIL score or lending decision.",
        "Synthetic source codes and fictional account references establish test evidence only, never real creditworthiness."])
    page = None
    y = 48
    for line in "\n".join(lines).splitlines():
        wrapped = textwrap.wrap(line, width=92, subsequent_indent="  ",
            replace_whitespace=False, drop_whitespace=False) or [""]
        for segment in wrapped:
            if page is None or y > 785:
                page = document.new_page()
                y = 48
            page.insert_text((48, y), segment, fontsize=8.5, fontname="courier")
            y += 11
    data = document.tobytes()
    document.close()
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="prism-assessment-{row.assessment_id}.pdf"'})
