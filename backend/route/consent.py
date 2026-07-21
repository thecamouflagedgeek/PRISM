from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.session_store import get_session

from database.db import get_db
from database.crud import save_consent

router = APIRouter()


class ConsentReq(BaseModel):
    session_id: str
    consent_bank: bool = True
    consent_salary: bool = False
    consent_utility: bool = False
    consent_dpdpa: bool = True


@router.post("/consent")
def consent(
    data: ConsentReq,
    db: Session = Depends(get_db)
):

    # -----------------------------
    # Validate Session
    # -----------------------------
    session = get_session(data.session_id)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session"
        )

    # -----------------------------
    # Mandatory Consents
    # -----------------------------
    if not data.consent_bank or not data.consent_dpdpa:
        raise HTTPException(
            status_code=403,
            detail="Bank Statement and DPDPA consent are mandatory."
        )

    # -----------------------------
    # Update Session
    # -----------------------------
    session.consent_bank = data.consent_bank
    session.consent_salary = data.consent_salary
    session.consent_utility = data.consent_utility
    session.consent_dpdpa = data.consent_dpdpa

    # -----------------------------
    # Save to PostgreSQL
    # -----------------------------
    save_consent(
        db=db,
        application_id=session.application_id,
        bank_consent=session.consent_bank,
        salary_consent=session.consent_salary,
        utility_consent=session.consent_utility,
        dpdpa_consent=session.consent_dpdpa
    )

    # -----------------------------
    # Response
    # -----------------------------
    return {
        "status": "success",
        "message": "Consent recorded successfully.",
        "session_id": session.session_id,
        "application_id": session.application_id,
        "consents": {
            "bank": session.consent_bank,
            "salary": session.consent_salary,
            "utility": session.consent_utility,
            "dpdpa": session.consent_dpdpa
        }
    }