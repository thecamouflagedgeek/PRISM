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

    # SCORING
    result = compute_risk_score(
        bank_features,
        salary_features,
        utility_features
    )
    session.assessment_result = result

    return {
        "status": "success",
        "assessed_at": datetime.utcnow().isoformat(),
        "session_id": session_id,
        **result
    }