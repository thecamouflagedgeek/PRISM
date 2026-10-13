import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.otp import generate_otp, verify_otp
from auth.store import verified_users

from core.session_store import create_session

from database.crud import (
    get_user_by_phone,
    create_user,
    create_application,
    save_audit_event,
)
from database.models import Application, BankCashflowAssessment, ExperimentalAssessment, RiskScore, Consent


def signup(
    db: Session,
    phone_number: str,
    role: str = "borrower",
):
    allowed_lenders = {value.strip() for value in os.getenv("PRISM_LENDER_PHONES", "").split(",") if value.strip()}
    if role == "lender" and phone_number not in allowed_lenders:
        raise HTTPException(status_code=403, detail="This phone number is not authorized for lender access")
    generate_otp(phone_number)

    return {
        "status": "success",
        "message": "OTP sent successfully"
    }


def verify(
    db: Session,
    phone_number: str,
    otp: str,
    role: str = "borrower",
):
    allowed_lenders = {value.strip() for value in os.getenv("PRISM_LENDER_PHONES", "").split(",") if value.strip()}
    if role == "lender" and phone_number not in allowed_lenders:
        return {"status": "failed", "message": "This phone number is not authorized for lender access"}
    if not verify_otp(phone_number, otp):

        return {
            "status": "failed",
            "message": "Invalid or expired OTP"
        }

    verified_users[phone_number] = True

    # -----------------------------
    # Find or create user
    # -----------------------------

    user = get_user_by_phone(
        db,
        phone_number
    )
    is_returning_user = user is not None

    if user is None:

        user = create_user(
            db,
            phone_number
        )

    application = None
    has_prior_assessments = False
    has_recorded_consent = False
    if role == "borrower":
        applications = db.query(Application).filter(Application.user_id == user.user_id).all()
        application_ids = {row.application_id for row in applications}
        saved_runs = []
        if application_ids:
            for model, timestamp_field in ((BankCashflowAssessment, BankCashflowAssessment.created_at),
                                           (ExperimentalAssessment, ExperimentalAssessment.created_at)):
                saved_runs.extend(db.query(model.application_id, timestamp_field)
                    .filter(model.application_id.in_(application_ids), model.user_id == user.user_id).all())
            saved_runs.extend(db.query(RiskScore.application_id, RiskScore.generated_at)
                .filter(RiskScore.application_id.in_(application_ids)).all())
        has_prior_assessments = bool(saved_runs)
        assessed_application_id = (max(saved_runs, key=lambda row: (row[1].timestamp() if row[1] else 0, row[0]))[0]
                                   if saved_runs else None)
        application = (db.query(Application).filter(Application.application_id == assessed_application_id).first()
                       if assessed_application_id is not None else None)
        if application is None and applications:
            application = max(applications, key=lambda row: row.application_id)
        if application is None:
            application = create_application(db, user.user_id)
            save_audit_event(db, application.application_id, "application_created", "application", "success")
        has_recorded_consent = db.query(Consent.consent_id).filter(Consent.application_id == application.application_id).first() is not None

    session = create_session(
        borrower_id=phone_number, user_id=user.user_id,
        application_id=application.application_id if application else None, role=role
    )

    return {"status": "success", "message": "OTP verified",
        "session_id": session.session_id,
        "application_id": application.application_id if application else None,
        "has_prior_assessments": has_prior_assessments,
        "is_returning_user": is_returning_user,
        "has_recorded_consent": has_recorded_consent,
        "role": role}
