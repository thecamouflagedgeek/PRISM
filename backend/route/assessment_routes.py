from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Depends, Form
import tempfile
import os
from datetime import datetime
import pandas as pd
from core.session_store import get_session
from ingestion.parsers.bank_parser import BankParser
from ingestion.parsers.salary_parser import SalaryParser
from ingestion.parsers.utility_parser import UtilityParser
from services.ocr_service import get_ocr_engine
from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer
from services.assessment_service import assess_borrower
from ingestion.document_pipeline import DocumentPipeline, DocumentProcessingError

import math
import numpy as np
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import Depends
from database.db import get_db
from database.crud import (save_document, update_document_status, save_features, save_risk_score,
    save_shap_explanations, save_assessment_details, mark_application_assessed, save_audit_event)
from database.models import Application
from database.models import AuditEvent
from scoring.risk_scorer import score_borrower
from pydantic import BaseModel
from features.financial_health import build_financial_health


router = APIRouter(prefix="/assess", tags=["Assessment"])

class WhatIfRequest(BaseModel):
    overrides: dict[str, float]


def mark_as_pending_frozen_scorecard(result: dict) -> dict:
    """Keep legacy document intelligence while withholding its unrelated score."""
    legacy_status = result.get("status")
    for key in ("display_score", "risk_score", "score", "pd", "probability_of_default",
                "risk_tier", "confidence", "credit_risk", "feature_contributions", "reason_codes"):
        result.pop(key, None)
    result.update({
        "status": "INSUFFICIENT_EXPERIMENTAL_EVIDENCE",
        "scoreable": False,
        "display_score": None,
        "pd": None,
        "probability_of_default": None,
        "risk_tier": None,
        "reason_codes": [],
        "model_validation_status": "PHASE_2B6_INCONCLUSIVE",
        "data_sufficiency": {"reasons": ["CREDIT_CARD_STATEMENT_AND_REPAYMENT_HISTORY_REQUIRED"],
            "message": "Uploaded supporting documents do not establish all four frozen model features."},
        "supporting_intelligence": {"legacy_pipeline_status": legacy_status,
            "credit_score_generated": False,
            "note": "Bank, salary, utility, document and fraud findings are supporting signals; they are not inputs to the frozen four-feature model."},
    })
    return result



# ---------------------------------------------------------------------------
# TEMP FILE HANDLING
# ---------------------------------------------------------------------------

async def save_temp(file: UploadFile):
    if file is None:
        return None

    if not file.filename:
        return None

    contents = await file.read()

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(415, "Supported document formats are PDF, JPG, JPEG, and PNG")

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    )

    tmp.write(contents)
    tmp.close()

    return tmp.name


def assert_valid_path(path, name="file"):
    if not path:
        raise ValueError(
            f"{name} path is missing (None received)"
        )


# ---------------------------------------------------------------------------
# GENERIC DOCUMENT PROCESSING
# ---------------------------------------------------------------------------

def process_doc(parser, engineer_cls, path, ocr_engine=None):
    """
    Existing generic document processing flow.

    Preserves the original behaviour:
        parser.extract()
        parser.transform()
        parser.validate()
        feature engineering

    Returns only engineered features.
    """
    raw = parser.extract(path, password=password)
    df = parser.transform(raw)

    parser.validate(df)

    engineer = engineer_cls(df)
    features = engineer.build_features()

    return features


# ---------------------------------------------------------------------------
# BANK DOCUMENT PROCESSING
# ---------------------------------------------------------------------------

def process_bank_doc(path, ocr_engine=None, password=None):
    """
    Process a bank document.

    Returns:
        bank_features
        bank_transactions

    bank_features:
        Engineered features used by the credit-risk model.

    bank_transactions:
        Canonical structured transaction DataFrame used by
        the fraud engine and document-intelligence layer.
    """

    parser = BankParser(ocr_engine)

    raw = parser.extract(path, password=password)

    transactions = parser.transform(raw)

    parser.validate(transactions)
    required = {"date", "amount", "type", "closing_balance"}
    if not isinstance(transactions, pd.DataFrame) or not required.issubset(transactions.columns):
        raise ValueError("Bank extraction did not produce the required transaction fields")
    valid_rows = (pd.to_datetime(transactions["date"], errors="coerce", dayfirst=True).notna()
        & pd.to_numeric(transactions["amount"], errors="coerce").notna()
        & transactions["type"].astype(str).str.upper().isin(["CR", "DR"]))
    if valid_rows.sum() < 1:
        raise ValueError("Bank extraction produced no valid dated transactions")
    parser.metadata["valid_transaction_coverage"] = float(valid_rows.mean())
    parser.metadata["quality_score"] = min(float(parser.metadata.get("quality_score", 0.0)),
        float(valid_rows.mean()))
    if valid_rows.mean() < 0.80:
        raise ValueError("Bank extraction has too many malformed transaction rows")
    transactions = transactions.loc[valid_rows].copy()

    features = BankFeatureEngineer(
        transactions
    ).build_features()

    return features, transactions, parser.metadata


# ---------------------------------------------------------------------------
# UTILITY DOCUMENT PROCESSING
# ---------------------------------------------------------------------------

def process_utility_doc(path, ocr_engine=None, password=None):
    """
    Process a utility document while preserving both:

        1. Engineered utility features
        2. Raw structured utility data

    The engineered features are used by the credit-risk model.

    The raw structured data is passed independently to the
    document-consistency layer.
    """

    parser = UtilityParser(ocr_engine)

    raw = parser.extract(path, password=password)

    utility_data = parser.transform(raw)

    parser.validate(utility_data)

    features = UtilityFeatureEngineer(
        utility_data
    ).build_features()

    return features, utility_data, parser.metadata


# ---------------------------------------------------------------------------
# JSON SERIALIZATION HELPERS
# ---------------------------------------------------------------------------

def clean_json(obj):
    """
    Recursively convert objects into JSON-safe values.
    """

    if isinstance(obj, dict):
        return {
            k: clean_json(v)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [
            clean_json(v)
            for v in obj
        ]

    if isinstance(obj, tuple):
        return [
            clean_json(v)
            for v in obj
        ]

    if isinstance(obj, pd.DataFrame):
        return clean_json(
            obj.to_dict(orient="records")
        )

    if isinstance(obj, pd.Series):
        return clean_json(
            obj.to_dict()
        )

    if isinstance(obj, np.generic):
        obj = obj.item()

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None

    return obj


def features_to_dict(features):
    """
    Convert feature-engineering outputs into JSON-safe dictionaries.
    """

    if features is None:
        return None

    if isinstance(features, dict):
        data = features

    elif hasattr(features, "model_dump"):
        # Pydantic v2
        data = features.model_dump()

    elif hasattr(features, "dict"):
        # Pydantic v1
        data = features.dict()

    elif hasattr(features, "to_dict"):
        data = features.to_dict()

    else:
        data = vars(features)

    return clean_json(data)


# ---------------------------------------------------------------------------
# ASSESSMENT ENDPOINT
# ---------------------------------------------------------------------------

@router.post("")
async def assess(
    bank_file: UploadFile = File(...),
    salary_file: UploadFile = File(None),
    utility_file: UploadFile = File(None),
    bank_password: str = Form(None),
    salary_password: str = Form(None),
    utility_password: str = Form(None),
    session_id: str = Header(...),
    ocr_engine=Depends(get_ocr_engine),
    db: Session = Depends(get_db),
):
    """
    Run the complete PRISM assessment.

    Pipeline:

        Bank document
            ↓
        Bank features + transactions
            ↓
        Credit Risk + Fraud Risk + Document Risk

        Salary document
            ↓
        Salary features + raw salary data
            ↓
        Credit Risk + Document Risk

        Utility document
            ↓
        Utility features + raw utility data
            ↓
        Credit Risk + Document Risk
    """

    # -----------------------------------------------------------------------
    # SESSION / CONSENT
    # -----------------------------------------------------------------------

    session = get_session(session_id)

    if not session:
        raise HTTPException(
            401,
            "Invalid session",
        )

    if not session.consent_bank:
        raise HTTPException(
            403,
            "Bank consent required",
        )

    # -----------------------------------------------------------------------
    # INITIALIZE DOCUMENT DATA
    # -----------------------------------------------------------------------

    bank_features = None
    bank_transactions = None

    salary_features = None
    salary_data = None

    utility_features = None
    utility_data = None
    bank_metadata = {"available": False, "extraction_status": "FAILED", "quality_score": 0.0}
    salary_metadata = {"available": False, "extraction_status": "FAILED", "quality_score": 0.0}
    utility_metadata = {"available": False, "extraction_status": "FAILED", "quality_score": 0.0}

    # -----------------------------------------------------------------------
    # BANK
    # -----------------------------------------------------------------------

    bank_path = await save_temp(bank_file)

    assert_valid_path(
        bank_path,
        "bank_file",
    )

    bank_document = None
    try:
        if session.application_id is not None:
            bank_document = save_document(db, session.application_id, "BANK_STATEMENT", bank_file.filename or "bank.pdf", bank_path)
            save_audit_event(db, session.application_id, "document_uploaded", "document", "success", {"document_type": "BANK_STATEMENT", "document_id": bank_document.document_id})
        try:
            bank_features, bank_transactions, bank_metadata = process_bank_doc(bank_path, ocr_engine, bank_password)
            if bank_document:
                update_document_status(db, bank_document.document_id, "OCR_COMPLETED")
            if session.application_id is not None:
                save_features(db, session.application_id, "BANK", features_to_dict(bank_features))
        except Exception as exc:
            # Freia's document pipeline exposes credit-card statement features,
            # but explicitly marks that document type unscoreable. Keep the
            # extraction available to review while retaining the active bank
            # account parser and scorecard gates.
            if "classified as CREDIT_CARD" in str(exc).upper() or "classified as CREDIT CARD" in str(exc).upper():
                try:
                    card_result = DocumentPipeline(ocr_engine=ocr_engine).process(bank_path)
                    if not card_result.is_scoreable:
                        bank_features = card_result.features
                        bank_transactions = card_result.transactions
                        bank_metadata = {"available": False, "extraction_status": "FAILED",
                            "quality_score": 0.0, "document_type": card_result.document_type,
                            "scoreable": False, "warning": "credit_card_model_not_available"}
                        if bank_document:
                            update_document_status(db, bank_document.document_id, "OCR_COMPLETED")
                        if session.application_id is not None:
                            save_features(db, session.application_id, "BANK", features_to_dict(bank_features))
                    else:
                        bank_metadata = {**bank_metadata, "warning": f"extraction_failed: {type(exc).__name__}"}
                except Exception as pipeline_exc:
                    if bank_document:
                        update_document_status(db, bank_document.document_id, "FAILED")
                    bank_metadata = {**bank_metadata, "warning": f"extraction_failed: {type(pipeline_exc).__name__}"}
            else:
                if bank_document:
                    update_document_status(db, bank_document.document_id, "FAILED")
                bank_metadata = {**bank_metadata, "warning": f"extraction_failed: {type(exc).__name__}"}

    finally:
        if os.path.exists(bank_path):
            os.remove(bank_path)

    # -----------------------------------------------------------------------
    # SALARY
    # -----------------------------------------------------------------------

    if salary_file and session.consent_salary:

        salary_path = await save_temp(
            salary_file
        )

        assert_valid_path(
            salary_path,
            "salary_file",
        )

        try:
            salary_document = (save_document(db, session.application_id, "SALARY_SLIP", salary_file.filename or "salary.pdf", salary_path)
                if session.application_id is not None else None)
            salary_parser = SalaryParser(ocr_engine)

            # Preserve raw structured salary data.
            try:
                salary_data = salary_parser.parse(salary_path, password=salary_password)
            except Exception:
                salary_data = None

            if (
                not salary_data
                or not isinstance(salary_data, dict)
            ):
                salary_data = None
            else:
                # Existing credit feature engineering.
                engineer = SalaryFeatureEngineer(salary_data)
                salary_features = engineer.build_features()
                if salary_document:
                    update_document_status(db, salary_document.document_id, "OCR_COMPLETED")
                if session.application_id is not None:
                    save_features(db, session.application_id, "SALARY", features_to_dict(salary_features))
                salary_fields = ("gross_salary", "net_salary")
                valid_salary_fields = all(salary_data.get(k) is not None for k in salary_fields)
                salary_metadata = {"available": True, "extraction_status": "SUCCESS" if valid_salary_fields else "FAILED",
                    "quality_score": salary_parser.metadata.get("extraction_confidence", 0.0) if valid_salary_fields else 0.0,
                    "method": salary_parser.metadata.get("method"), "text_length": salary_parser.metadata.get("text_length"),
                    "extracted_fields": [k for k, v in salary_data.items() if v is not None]}

        finally:
            if os.path.exists(salary_path):
                os.remove(salary_path)

    # -----------------------------------------------------------------------
    # UTILITY
    # -----------------------------------------------------------------------

    if utility_file and session.consent_utility:

        utility_path = await save_temp(
            utility_file
        )

        assert_valid_path(
            utility_path,
            "utility_file",
        )

        utility_document = (save_document(db, session.application_id, "UTILITY_BILL", utility_file.filename or "utility.pdf", utility_path)
            if session.application_id is not None else None)
        try:
            # Preserve BOTH:
            #   utility_features
            #   utility_data
            utility_features, utility_data, utility_metadata = process_utility_doc(utility_path, ocr_engine, utility_password)
            if utility_document:
                update_document_status(db, utility_document.document_id, "OCR_COMPLETED")
            if session.application_id is not None:
                save_features(db, session.application_id, "UTILITY", features_to_dict(utility_features))
        except Exception as exc:
            if utility_document:
                update_document_status(db, utility_document.document_id, "FAILED")
            utility_metadata = {**utility_metadata, "warning": f"extraction_failed: {type(exc).__name__}"}

        finally:
            if os.path.exists(utility_path):
                os.remove(utility_path)

    # -----------------------------------------------------------------------
    # ASSESSMENT
    # -----------------------------------------------------------------------

    # Evidence metrics are explicit; missing documents and failed extraction
    # remain unavailable and block the credit model.
    tx_count = len(bank_transactions) if bank_transactions is not None else 0
    history_days = 0
    bank_age_days = None
    if bank_transactions is not None and not bank_transactions.empty and "date" in bank_transactions:
        dates = pd.to_datetime(bank_transactions["date"], errors="coerce", dayfirst=True).dropna()
        if not dates.empty:
            history_days = max(0, int((dates.max() - dates.min()).days))
            bank_age_days = max(0, int((datetime.utcnow().date() - dates.max().date()).days))
            bank_metadata["date_range"] = {"start": dates.min().date().isoformat(), "end": dates.max().date().isoformat()}
            bank_metadata["future_dated"] = bool(dates.max().date() > datetime.utcnow().date())
    bank_metadata["extracted_fields"] = sorted(list(bank_transactions.columns)) if bank_transactions is not None else []
    bank_metadata.update({"available": bank_transactions is not None and tx_count > 0,
        "extraction_status": "SUCCESS" if bank_transactions is not None and tx_count else "FAILED",
        "transaction_count": tx_count, "history_days": history_days, "age_days": bank_age_days})
    utility_metadata.update({"available": utility_data is not None,
        "extraction_status": "SUCCESS" if utility_data is not None else "FAILED"})
    utility_metadata["extracted_fields"] = sorted(list(utility_data.columns)) if isinstance(utility_data, pd.DataFrame) else []
    utility_metadata["observation_count"] = len(utility_data) if isinstance(utility_data, pd.DataFrame) else 0
    if isinstance(utility_data, pd.DataFrame) and "payment_date" in utility_data:
        utility_dates = pd.to_datetime(utility_data["payment_date"], errors="coerce", dayfirst=True).dropna()
        if not utility_dates.empty:
            utility_metadata["age_days"] = max(0, int((datetime.utcnow().date() - utility_dates.max().date()).days))
            utility_metadata["future_dated"] = bool(utility_dates.max().date() > datetime.utcnow().date())
    if isinstance(salary_data, dict):
        salary_date = next((salary_data.get(key) for key in ("pay_date", "payslip_date", "date") if salary_data.get(key)), None)
        parsed_salary_date = pd.to_datetime(salary_date, errors="coerce", dayfirst=True) if salary_date else pd.NaT
        if not pd.isna(parsed_salary_date):
            salary_metadata["age_days"] = max(0, int((datetime.utcnow().date() - parsed_salary_date.date()).days))
            salary_metadata["future_dated"] = bool(parsed_salary_date.date() > datetime.utcnow().date())
    if bank_metadata.get("quality_score") is None:
        bank_metadata["quality_score"] = bank_metadata.get("extraction_confidence", 0.0)
    if utility_metadata.get("quality_score") is None:
        utility_metadata["quality_score"] = utility_metadata.get("extraction_confidence", 0.0)
    evidence = {"bank": bank_metadata, "salary": salary_metadata, "utility": utility_metadata,
        "feature_sources": {"credit_debit_ratio": "bank_statement.transactions", "cashflow_cv": "bank_statement.transactions",
            "min_balance": "bank_statement.closing_balance", "net_to_gross_ratio": "salary_document.gross_salary/net_salary",
            "utility_stability": "utility_document.payment_history"}}

    financial_health = build_financial_health(bank_transactions, extraction=bank_metadata)

    result = assess_borrower(

        # ---------------------------------------------------------------
        # Existing engineered features
        # Used by the credit-risk scorecard.
        # ---------------------------------------------------------------

        bank=bank_features,
        salary=salary_features,
        utility=utility_features,

        # ---------------------------------------------------------------
        # Identity/history
        #
        # This upload-only endpoint currently does not have borrower
        # identity/history information.
        #
        # Do NOT use session_id as borrower identity.
        # ---------------------------------------------------------------

        application={},
        application_history=[],

        # ---------------------------------------------------------------
        # Existing fraud input
        # ---------------------------------------------------------------

        transactions=bank_transactions,

        # ---------------------------------------------------------------
        # Raw structured document inputs
        #
        # These are used ONLY by the document-consistency layer.
        # ---------------------------------------------------------------

        bank_document=bank_transactions,
        salary_document=salary_data,
        utility_document=utility_data,
        evidence=evidence,
    )

    # The borrower upload form collects supporting bank/salary/utility records,
    # not validated credit-card repayment evidence. Never expose the legacy
    # cash-flow score as the frozen four-feature research scorecard.
    result = mark_as_pending_frozen_scorecard(result)

    # -----------------------------------------------------------------------
    # STORE ASSESSMENT
    # -----------------------------------------------------------------------

    session.assessment_result = result
    session.evidence = evidence
    session.bank_features = bank_features
    session.salary_features = salary_features
    session.utility_features = utility_features
    session.bank_transactions = bank_transactions
    session.salary_document = salary_data
    session.utility_document = utility_data

    # Persist only an actual score. Insufficient-evidence outcomes stay visible
    # to the borrower and lender without manufacturing numeric values.
    if (session.application_id is not None and result.get("status") == "SCORED"
            and result.get("display_score") is not None and result.get("pd") is not None):
        persisted = {**result, "risk_score": result["display_score"], "probability_of_default": result["pd"]}
        score_row = save_risk_score(db, session.application_id, persisted)
        contributions = result.get("feature_contributions", {})
        explanations = [{"feature_name": name, "shap_value": None, "score_contribution": value,
            "contribution_type": "Scorecard contribution", "feature_rank": rank,
            "generated_reason": f"{name.replace('_', ' ')} scorecard contribution."}
            for rank, (name, value) in enumerate(sorted(contributions.items(), key=lambda pair: abs(pair[1]), reverse=True), 1)]
        if explanations:
            save_shap_explanations(db, score_row.score_id, explanations)
        save_assessment_details(db, session.application_id, score_row.score_id,
            result.get("fraud_risk", {}), result.get("document_risk", {}))
        mark_application_assessed(db, session.application_id)
        save_audit_event(db, session.application_id, "assessment_scored", "assessment", "success", {"score_id": score_row.score_id})
    elif session.application_id is not None:
        application = db.query(Application).filter(Application.application_id == session.application_id).first()
        if application:
            application.application_status = "INSUFFICIENT_EVIDENCE"
            db.commit()
        save_audit_event(db, session.application_id, "assessment_completed", "assessment", "pending", {"status": result.get("status"), "reason_codes": result.get("data_sufficiency", {}).get("reasons", [])})

    if session.application_id is not None:
        # The summary is intentionally aggregate-only: no narrations, account identifiers,
        # or transaction rows are stored in the audit record.
        health_event = save_audit_event(db, session.application_id, "financial_document_analysis", "financial_health",
            "success" if financial_health["status"] == "AVAILABLE" else "unavailable", financial_health)
        financial_health["analysis_id"] = health_event.event_id

    # -----------------------------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------------------------

    response = {
        "status": result.get("status", "INSUFFICIENT_DATA").lower(),
        "scoreable": result.get("status") == "SCORED",
        "application_id": session.application_id,
        "assessment_id": None,
        "assessment_status": "INSUFFICIENT_EVIDENCE",
        "model_version": None,
        "score": None,
        "probability_of_default": None,
        "risk_tier": None,
        # Coverage is the share of the four frozen features that are present,
        # finite, provenance-valid, and derived from approved evidence.
        "feature_coverage": 0.0,
        "feature_values": None,
        "woe_values": None,
        "feature_contributions": None,
        "improvement_recommendations": [],
        "document_findings": evidence,
        "fraud_findings": result.get("fraud_risk"),
        "assessment_timestamp": datetime.utcnow().isoformat(),
        "document_type": bank_metadata.get("document_type", "savings_account" if bank_transactions is not None else "unknown"),
        "assessed_at": datetime.utcnow().isoformat(),
        "session_id": session_id,

        **result,

        "features": {
            "bank": features_to_dict(
                bank_features
            ),
            "salary": features_to_dict(
                salary_features
            ),
            "utility": features_to_dict(
                utility_features
            ),
        },
        "extraction": evidence,
        "financial_health": financial_health,
    }

    # -----------------------------------------------------------------------
    # NaN DEBUG CHECK
    # -----------------------------------------------------------------------

    def find_nan(obj, path="root"):

        if isinstance(obj, dict):

            for key, value in obj.items():
                find_nan(
                    value,
                    f"{path}.{key}",
                )

        elif isinstance(obj, list):

            for index, value in enumerate(obj):
                find_nan(
                    value,
                    f"{path}[{index}]",
                )

        elif isinstance(obj, float):

            if math.isnan(obj):
                print(
                    "NaN found at:",
                    path,
                )

    response = clean_json(response)
    find_nan(response)

    return response


@router.get("/financial-health/latest")
def latest_financial_health(session_id: str = Header(...), db: Session = Depends(get_db)):
    """Return the authenticated borrower's latest application-scoped aggregate findings."""
    session = get_session(session_id)
    if not session or not session.is_authenticated or session.role != "borrower":
        raise HTTPException(401, "Borrower session required")
    if session.application_id is None or session.user_id is None:
        raise HTTPException(404, "No application financial findings are available")
    application = (db.query(Application).filter(Application.application_id == session.application_id)
                   .filter(Application.user_id == session.user_id).first())
    if application is None:
        raise HTTPException(404, "Application not found")
    event = (db.query(AuditEvent).filter(AuditEvent.application_id == application.application_id)
             .filter(AuditEvent.action == "financial_document_analysis")
             .order_by(AuditEvent.event_timestamp.desc()).first())
    if event is None:
        raise HTTPException(404, "No financial document analysis is available")
    return {**(event.details or {}), "analysis_id": event.event_id, "analyzed_at": event.event_timestamp.isoformat()}


@router.post("/whatif")
async def whatif(payload: WhatIfRequest, session_id: str = Header(...)):
    session = get_session(session_id)
    if not session:
        raise HTTPException(401, "Invalid session")
    if not getattr(session, "assessment_result", None) or session.assessment_result.get("status") != "SCORED":
        raise HTTPException(400, "A scored assessment is required before what-if simulation")
    bank = dict(session.bank_features or {})
    salary = dict(session.salary_features or {})
    utility = dict(session.utility_features or {})
    target_map = {"credit_debit_ratio": (bank, "credit_debit_ratio"), "cashflow_cv": (bank, "cashflow_cv"),
        "min_balance": (bank, "min_balance_l3m"), "net_to_gross_ratio": (salary, "net_to_gross_ratio"),
        "utility_stability": (utility, "utility_stability")}
    for name, value in payload.overrides.items():
        if name in target_map:
            target, key = target_map[name]
            target[key] = value
    simulated = score_borrower(bank=bank, salary=salary, utility=utility, evidence=getattr(session, "evidence", {}))
    base = session.assessment_result
    if simulated.get("status") != "SCORED":
        raise HTTPException(422, "The proposed values did not pass the scorecard evidence and feature checks")
    base_score = base.get("display_score")
    new_score = simulated.get("display_score")
    return {"status": "success", "base_score": base_score, "new_score": new_score,
        "delta": round(new_score - base_score, 2), "base_tier": base.get("risk_tier"),
        "delta_tier": simulated.get("risk_tier") if simulated.get("risk_tier") != base.get("risk_tier") else None,
        "probability_of_default": simulated.get("pd"), "pd_type": simulated.get("pd_type")}
