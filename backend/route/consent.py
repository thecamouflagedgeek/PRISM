from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.session_store import create_session

router = APIRouter()

class ConsentReq(BaseModel):
    borrower_id: str
    consent_bank: bool = True
    consent_salary: bool = False
    consent_utility: bool = False
    consent_dpdpa: bool = True


@router.post("/consent")
def consent(data: ConsentReq):

    if not data.consent_bank or not data.consent_dpdpa:
        raise HTTPException(403, "Bank + DPDPA consent required")

    session = create_session(data.borrower_id)

    session.consent_bank = True
    session.consent_salary = data.consent_salary
    session.consent_utility = data.consent_utility
    session.consent_dpdpa = True

    return {
        "session_id": session.session_id,
        "message": "Consent recorded"
    }