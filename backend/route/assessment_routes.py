from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Depends
import tempfile
import os
from datetime import datetime

from core.session_store import get_session

from ingestion.parsers.bank_parser import BankParser
from ingestion.parsers.salary_parser import SalaryParser
from ingestion.parsers.utility_parser import UtilityParser

from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer

from services.ocr_service import get_ocr_engine

from scoring.risk_scorer import compute_risk_score

router = APIRouter(prefix="/assess", tags=["Assessment"])


def save_temp(file: UploadFile):

    if file is None:
        return None

    if not file.filename:
        return None

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    )

    tmp.write(file.file.read())
    tmp.close()

    return tmp.name


def process_doc(parser, engineer_cls, path):

    raw = parser.extract(path)

    print("\nRAW DATA")
    print(raw.head() if hasattr(raw, "head") else raw)

    df = parser.transform(raw)

    print("\nTRANSFORMED DF")
    print(df.head())
    print(df.columns)

    parser.validate(df)

    engineer = engineer_cls(df)

    return engineer.build_features()


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
        raise HTTPException(
            status_code=401,
            detail="Invalid session"
        )

    if not session.consent_bank:
        raise HTTPException(
            status_code=403,
            detail="Bank consent required"
        )

    bank_features = None
    salary_features = None
    utility_features = None

    # ---------------- BANK ----------------

    bank_path = save_temp(bank_file)

    try:

        bank_features = process_doc(
            BankParser(),
            BankFeatureEngineer,
            bank_path
        )

    finally:

        if bank_path and os.path.exists(bank_path):
            os.remove(bank_path)

    # ---------------- SALARY ----------------

    if salary_file and session.consent_salary:

        salary_path = save_temp(salary_file)

        try:

            salary_parser = SalaryParser(
                ocr_engine
            )

            salary_df = salary_parser.parse(
                salary_path
            )

            salary_engineer = SalaryFeatureEngineer(
                salary_df
            )

            salary_features = (
                salary_engineer.build_features()
            )

        finally:

            if salary_path and os.path.exists(salary_path):
                os.remove(salary_path)

    # ---------------- UTILITY ----------------

    if utility_file and session.consent_utility:

        utility_path = save_temp(
            utility_file
        )

        try:

            utility_parser = UtilityParser()

            utility_df = utility_parser.transform(
                utility_parser.extract(
                    utility_path
                )
            )

            utility_engineer = UtilityFeatureEngineer(
                utility_df
            )

            utility_features = (
                utility_engineer.build_features()
            )

        finally:

            if utility_path and os.path.exists(utility_path):
                os.remove(utility_path)

    # ---------------- SCORE ----------------

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