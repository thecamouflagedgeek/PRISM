from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Depends, Form
from fastapi.responses import JSONResponse

import tempfile
import os
import json
from datetime import datetime

import numpy as np
import pandas as pd

from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.db import get_db
from database.crud import (
    save_document,
    update_document_status,
    save_features,
    save_risk_score,
    save_shap_explanations,
)

from core.session_store import get_session

from services.ocr_service import get_ocr_engine

from ingestion.bank_transaction_pipeline import (
    BankTransactionPipeline,
    BankTransactionPipelineError,
)
from ingestion.document_pipeline import (
    DocumentPipeline,
    DocumentProcessingError,
)
from ingestion.document.classifier import is_credit_card_statement
from ingestion.extractors.credit_card_summary import extract_credit_card_summary
from ingestion.extractors.table import parse_credit_card_transactions

from ingestion.parsers.salary_parser import (
    SalaryParser,
    SalaryParsingError,
)
from ingestion.parsers.utility_parser import (
    UtilityParser,
    ExtractionQualityError as UtilityExtractionQualityError,
)
from ingestion.parsers.bank_parser import (
    ExtractionQualityError,
    ExtractionQualityError as BankExtractionQualityError,
)

from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer
from features.credit_card_features import CreditCardFeatureEngineer

from scoring.risk_scorer import (
    compute_risk_score,
    simulate_whatif,
)

router = APIRouter(prefix="/assess", tags=["Assessment"])


# ---------------------------------------------------------------------------
# JSON safety boundary
# ---------------------------------------------------------------------------
# This is the ONLY place responsible for making arbitrary python/numpy/pandas
# objects JSON-safe. It's applied via a single helper (`safe_response`) at
# every `return` in this router, so there is no code path that can hand
# FastAPI's jsonable_encoder a raw numpy/pandas object.
#
# Why json.dumps(default=...) instead of a hand-written recursive walker:
# a recursive walker (isinstance(obj, dict) / isinstance(obj, list) / ...)
# silently returns unrecognized types unchanged if you miss a branch (this is
# exactly what happened before: sets and raw np.bool_ inside them slipped
# through). json.dumps calls `default` on *every* value it doesn't already
# know how to serialize, with no way to skip one silently — if something is
# still wrong, this raises a clear TypeError naming the exact bad object
# instead of FastAPI's confusing double-exception.
class WhatIfRequest(BaseModel):
    overrides: dict[str, float]

def _json_default(obj):
    # numpy scalars: bool_, int8..int64, float16..float64, etc. -- one check
    # catches all of them instead of enumerating np.bool_/np.integer/np.floating.
    if isinstance(obj, np.generic):
        item = obj.item()
        if isinstance(item, float) and np.isnan(item):
            return None
        return item

    if isinstance(obj, np.ndarray):
        return obj.tolist()

    if isinstance(obj, (pd.Series, pd.Index)):
        return obj.tolist()

    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")

    if isinstance(obj, (set, frozenset)):
        return list(obj)

    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()

    if isinstance(obj, float) and np.isnan(obj):
        return None

    # Pydantic v2 / v1 models that reach here un-dumped
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()

    # Last resort: expose the object's __dict__ if it has one, so at least
    # the failure is informative rather than opaque.
    if hasattr(obj, "__dict__"):
        return vars(obj)

    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable: {obj!r}")


def safe_response(data: dict, status_code: int = 200) -> JSONResponse:
    """
    Round-trips `data` through json.dumps/json.loads using _json_default so
    that every leaf value is guaranteed to be a plain JSON-safe python type
    before FastAPI ever sees it. Use this for every return in this router
    instead of returning a bare dict.
    """
    cleaned = json.loads(json.dumps(data, default=_json_default))
    return JSONResponse(content=cleaned, status_code=status_code)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def save_temp(file: UploadFile):
    if file is None:
        return None
    if not file.filename:
        return None
    contents = await file.read()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(contents)
    tmp.close()
    return tmp.name


def assert_valid_path(path, name="file"):
    if not path:
        raise ValueError(f"{name} path is missing (None received)")


def process_doc(parser, engineer_cls, path, password=None):
    try:
        raw = parser.extract(path, password=password)
    except (BankExtractionQualityError, UtilityExtractionQualityError) as e:
        raise HTTPException(
            422,
            detail={"error": "extraction_quality_insufficient", "message": str(e), "issues": e.issues},
        )
    df = parser.transform(raw)
    parser.validate(df)
    try:
        engineer = engineer_cls(df)
        features = engineer.build_features()
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "feature_engineering_failed",
                "message": "Failed to compute features from extracted data.",
                "issues": str(e),
            },
        )
    return features


def features_to_dict(features):
    """Unwrap a features object into a plain dict. Does NOT need to worry
    about numpy/pandas leaf types anymore -- safe_response handles that."""
    if features is None:
        return None
    if isinstance(features, dict):
        return features
    if hasattr(features, "model_dump"):      # Pydantic v2
        return features.model_dump()
    if hasattr(features, "dict"):            # Pydantic v1
        return features.dict()
    if hasattr(features, "to_dict"):         # pandas
        return features.to_dict()
    return vars(features)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("")
async def assess(
    bank_file: UploadFile = File(...),
    salary_file: UploadFile = File(None),
    utility_file: UploadFile = File(None),
    bank_password: str = Form(None),
    utility_password: str = Form(None),
    session_id: str = Header(...),
    ocr_engine=Depends(get_ocr_engine),
    db: Session = Depends(get_db),
):
    session = get_session(session_id)
    if not session:
        raise HTTPException(401, "Invalid session")
    if not session.consent_bank:
        raise HTTPException(403, "Bank consent required")

    # ---------------- BANK ----------------
    bank_path = await save_temp(bank_file)
    document = save_document(
    db=db,
    application_id=session.application_id,
    document_type="BANK_STATEMENT",
    file_name=bank_file.filename,
    storage_path=bank_path,
)
    assert_valid_path(bank_path, "bank_file")
    try:
        pipeline = DocumentPipeline(ocr_engine=ocr_engine)
        try:
            pipeline_result = pipeline.process(bank_path, password=bank_password)
            update_document_status(
            db=db,
            document_id=document.document_id,
            status="OCR_COMPLETED"
        )
        except DocumentProcessingError as e:

            print("\n========== DOCUMENT PROCESSING ERROR ==========")
            print("Error Code:", e.error_code)
            print("Message:", e.message)
            print("Issues:", e.issues)
            print("=============================================\n")

            update_document_status(
                db=db,
                document_id=document.document_id,
                status="FAILED"
            )

            raise HTTPException(
                status_code=422,
                detail={
                    "error": e.error_code,
                    "message": e.message,
                    "issues": e.issues,
                },
            )
    finally:
        os.remove(bank_path)

    if not pipeline_result.is_scoreable:
        # NOTE: this branch previously returned pipeline_result.features raw,
        # bypassing all cleaning. That's the most likely source of the
        # numpy.bool_ crash. It now goes through safe_response like every
        # other return in this function.
        return safe_response({
            "status": "success",
            "assessed_at": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "document_type": pipeline_result.document_type,
            "scoreable": False,
            "note": (
                f"This is a {pipeline_result.document_type.replace('_', ' ')}. "
                "PRISM's credit scorecard is currently calibrated for savings/current "
                "account statements only. Extracted features are provided for reference, "
                "but no risk_score is generated for this document type yet."
            ),
            "features": {
                "bank": features_to_dict(pipeline_result.features),
                "salary": None,
                "utility": None,
            },
        })

    bank_features = pipeline_result.features
    save_features(
    db=db,
    application_id=session.application_id,
    feature_source="BANK",
    features=features_to_dict(bank_features)
)

    # ---------------- SALARY ----------------
    salary_features = None

    if salary_file and session.consent_salary:

        salary_path = await save_temp(salary_file)

        salary_document = save_document(
            db=db,
            application_id=session.application_id,
            document_type="SALARY_SLIP",
            file_name=salary_file.filename,
            storage_path=salary_path,
        )

        try:

            salary_parser = SalaryParser(ocr_engine)

            try:
                salary_data = salary_parser.parse(salary_path)

            except SalaryParsingError as e:

                update_document_status(
                    db=db,
                    document_id=salary_document.document_id,
                    status="FAILED"
                )

                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "salary_parsing_failed",
                        "message": str(e)
                    },
                )

            engineer = SalaryFeatureEngineer(salary_data)

            salary_features = engineer.build_features()

            update_document_status(
                db=db,
                document_id=salary_document.document_id,
                status="OCR_COMPLETED"
            )

            save_features(
                db=db,
                application_id=session.application_id,
                feature_source="SALARY",
                features=features_to_dict(salary_features)
            )

        finally:
            os.remove(salary_path)

        # ---------------- UTILITY ----------------
    utility_features = None

    if utility_file and session.consent_utility:

        utility_path = await save_temp(utility_file)

        utility_document = save_document(
            db=db,
            application_id=session.application_id,
            document_type="UTILITY_BILL",
            file_name=utility_file.filename,
            storage_path=utility_path,
        )

        assert_valid_path(utility_path, "utility_file")

        try:

            utility_features = process_doc(
                UtilityParser(ocr_engine),
                UtilityFeatureEngineer,
                utility_path,
            )

            update_document_status(
                db=db,
                document_id=utility_document.document_id,
                status="OCR_COMPLETED"
            )

            save_features(
                db=db,
                application_id=session.application_id,
                feature_source="UTILITY",
                features=features_to_dict(utility_features)
            )

        except Exception:

            update_document_status(
                db=db,
                document_id=utility_document.document_id,
                status="FAILED"
            )

            raise

        finally:
            os.remove(utility_path)

    # ---------------- SCORING ----------------
    result = compute_risk_score(
    bank_features,
    salary_features,
    utility_features
)

    score = save_risk_score(
        db=db,
        application_id=session.application_id,
        result=result,
    )

    save_shap_explanations(
        db=db,
        score_id=score.score_id,
        explanations=result["shap_explanations"],
    )

    session.assessment_result = result

    response_data = {
        "status": "success",
        "assessed_at": datetime.utcnow().isoformat(),
        "session_id": session_id,
        **result,
        "features": {
            "bank": features_to_dict(bank_features),
            "salary": features_to_dict(salary_features),
            "utility": features_to_dict(utility_features),
        },
    }

    return safe_response(response_data)

@router.post("/whatif")
async def whatif(payload: WhatIfRequest, session_id: str = Header(...)):
    session = get_session(session_id)
    if not session:
        raise HTTPException(401, "Invalid session")
    if not getattr(session, "assessment_result", None):
        raise HTTPException(400, "Run /assess for this session before using /assess/whatif")

    result = simulate_whatif(
        getattr(session, "bank_features", None),
        getattr(session, "salary_features", None),
        getattr(session, "utility_features", None),
        payload.overrides,
    )

    return safe_response({
        "status": "success",
        "session_id": session_id,
        **result,
    })