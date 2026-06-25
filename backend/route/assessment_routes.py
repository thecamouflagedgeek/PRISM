from fastapi import APIRouter, UploadFile, File, Header, HTTPException
from typing import List
import tempfile
import os
from datetime import datetime

from core.session_store import get_session

from ingestion.universal_pipeline import UniversalParser
from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer

from scoring.risk_scorer import compute_risk_score

router = APIRouter(prefix="/assess", tags=["Assessment"])


def save_temp(file: UploadFile):
    if file is None or not file.filename:
        return None

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    )

    tmp.write(file.file.read())
    tmp.close()

    return tmp.name


_parser = UniversalParser()


@router.post("")
async def assess(
    files: List[UploadFile] = File(...),
    session_id: str = Header(...),
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

    for file in files:
        file_path = save_temp(file)
        if not file_path:
            continue

        try:
            doc_type, mapped_data = _parser.process(file_path)

            if doc_type == "BANK":
                engineer = BankFeatureEngineer(mapped_data)
                bank_features = engineer.build_features()

            elif doc_type == "SALARY" and session.consent_salary:
                engineer = SalaryFeatureEngineer(mapped_data)
                salary_features = engineer.build_features()

            elif doc_type == "UTILITY" and session.consent_utility:
                engineer = UtilityFeatureEngineer(mapped_data)
                utility_features = engineer.build_features()

            elif doc_type == "UNKNOWN":
                raise ValueError("Could not confidently classify document type.")

        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed processing {file.filename}: {str(e)}"
            )
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    if not bank_features:
        raise HTTPException(
            status_code=400,
            detail="A valid bank statement is strictly required but none was identified."
        )

    result = compute_risk_score(
        bank_features,
        salary_features,
        utility_features,
    )

    session.assessment_result = result

    return {
        "status": "success",
        "assessed_at": datetime.utcnow().isoformat(),
        "session_id": session_id,
        **result,
    }