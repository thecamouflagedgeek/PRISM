from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Depends
import tempfile, os
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
from scoring.risk_scorer import compute_risk_score
import math
import numpy as np
router = APIRouter(prefix="/assess", tags=["Assessment"])


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


def process_doc(parser, engineer_cls, path, ocr_engine=None):
    raw = parser.extract(path)
    df = parser.transform(raw)

    parser.validate(df)
    engineer = engineer_cls(df)
    features = engineer.build_features()
    return features


def clean_json(obj):
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [clean_json(v) for v in obj]

    if isinstance(obj, np.generic):
        obj = obj.item()

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None

    return obj

def features_to_dict(features):
    if features is None:
        return None

    if isinstance(features, dict):
        data = features

    elif hasattr(features, "model_dump"):      # Pydantic v2
        data = features.model_dump()

    elif hasattr(features, "dict"):            # Pydantic v1
        data = features.dict()

    elif hasattr(features, "to_dict"):         # pandas
        data = features.to_dict()

    else:
        data = vars(features)

    return clean_json(data)


@router.post("")
async def assess(
    bank_file: UploadFile = File(...),
    salary_file: UploadFile = File(None),
    utility_file: UploadFile = File(None),
    session_id: str = Header(...),
    ocr_engine=Depends(get_ocr_engine)
):
    session = get_session(session_id)
    if not session:
        raise HTTPException(401, "Invalid session")
    if not session.consent_bank:
        raise HTTPException(403, "Bank consent required")

    # BANK
    bank_path = await save_temp(bank_file)
    assert_valid_path(bank_path, "bank_file")
    try:
        bank_features = process_doc(
            BankParser(),
            BankFeatureEngineer,
            bank_path
        )
    finally:
        os.remove(bank_path)

    # SALARY
    salary_features = None
    if salary_file and session.consent_salary:
        salary_path = await save_temp(salary_file)
        try:
            salary_parser = SalaryParser(ocr_engine)
            salary_data = salary_parser.parse(salary_path)

            if not salary_data or not isinstance(salary_data, dict):
                raise HTTPException(422, "Salary parsing failed")

            engineer = SalaryFeatureEngineer(salary_data)
            salary_features = engineer.build_features()
        finally:
            os.remove(salary_path)

    # UTILITY
    utility_features = None
    if utility_file and session.consent_utility:
        utility_path = await save_temp(utility_file)
        assert_valid_path(utility_path, "utility_file")
        try:
            utility_features = process_doc(
                UtilityParser(),
                UtilityFeatureEngineer,
                utility_path
            )
        finally:
            os.remove(utility_path)

    # SCORING
    result = compute_risk_score(
        bank_features,
        salary_features,
        utility_features
    )
    session.assessment_result = result
    
    response = {
    "status": "success",
    "assessed_at": datetime.utcnow().isoformat(),
    "session_id": session_id,
    **result,
    "features": {
        "bank": features_to_dict(bank_features),
        "salary": features_to_dict(salary_features),
        "utility": features_to_dict(utility_features),},
    }
    
    def find_nan(obj, path="root"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                find_nan(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                find_nan(v, f"{path}[{i}]")
        elif isinstance(obj, float):
            if math.isnan(v := obj):
                print("NaN found at:", path)
    find_nan(response)
    print(response)
    return response

    