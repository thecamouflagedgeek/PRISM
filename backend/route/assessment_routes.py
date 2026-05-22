from fastapi import APIRouter, UploadFile, File, Header, HTTPException
import tempfile, os
from datetime import datetime

from core.session_store import get_session
from ingestion.parsers.bank_parser import BankParser
from ingestion.parsers.salary_parser import SalaryParser
from ingestion.parsers.utility_parser import UtilityParser

from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer
from scoring.risk_scorer import compute_risk_score

router = APIRouter(prefix="/assess", tags=["Assessment"])

def save_temp(file: UploadFile):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(file.file.read())
    tmp.close()
    return tmp.name

def process_doc(parser, engineer_cls, path):
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
    session_id: str = Header(...)
):

    session = get_session(session_id)

    if not session:
        raise HTTPException(401, "Invalid session")

    if not session.consent_bank:
        raise HTTPException(403, "Bank consent required")

    #BANK
    bank_path = save_temp(bank_file)
    try:
        bank_features = process_doc(
            BankParser(),
            BankFeatureEngineer,
            bank_path
        )
    finally:
        os.remove(bank_path)

    #SALARY
    salary_features = None
    if salary_file and session.consent_salary:
        salary_path = save_temp(salary_file)
        try:
            salary_features = process_doc(
                SalaryParser(),
                SalaryFeatureEngineer,
                salary_path
            )
        finally:
            os.remove(salary_path)

    #UTILITY
    utility_features = None
    if utility_file and session.consent_utility:
        utility_path = save_temp(utility_file)
        try:
            utility_features = process_doc(
                UtilityParser(),
                UtilityFeatureEngineer,
                utility_path
            )
        finally:
            os.remove(utility_path)

    #SCORING
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