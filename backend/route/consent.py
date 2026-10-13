from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.session_store import get_session

from database.db import get_db
from database.crud import save_consent, save_audit_event

router = APIRouter()


@router.get('/consent')
def current_consent(session_id: str = Header(...), db: Session = Depends(get_db)):
    from route.experimental_assessment_routes import _session_owner
    from database.models import Consent
    session, application = _session_owner(session_id, db)
    row = db.query(Consent).filter_by(application_id=application.application_id).one()
    return {'bank': row.bank_consent, 'salary': row.salary_consent,
            'utility': row.utility_consent, 'dpdpa': row.dpdpa_consent, 'bureau': False}


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
    save_audit_event(db, session.application_id, "consent_recorded", "consent", "success",
        {"bank": session.consent_bank, "salary": session.consent_salary, "utility": session.consent_utility, "dpdpa": session.consent_dpdpa})

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
