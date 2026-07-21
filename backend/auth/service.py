from sqlalchemy.orm import Session

from auth.otp import generate_otp, verify_otp
from auth.store import verified_users

from core.session_store import create_session

from database.crud import (
    get_user_by_phone,
    create_user,
    create_application
)


def signup(
    db: Session,
    phone_number: str
):

    generate_otp(phone_number)

    return {
        "status": "success",
        "message": "OTP sent successfully"
    }


def verify(
    db: Session,
    phone_number: str,
    otp: str
):

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

    if user is None:

        user = create_user(
            db,
            phone_number
        )

    # -----------------------------
    # Create new application
    # -----------------------------

    application = create_application(
        db,
        user.user_id
    )

    # -----------------------------
    # Create session
    # -----------------------------

    session = create_session(
        borrower_id=phone_number,
        user_id=user.user_id,
        application_id=application.application_id
    )

    return {
        "status": "success",
        "message": "OTP verified",
        "session_id": session.session_id,
        "application_id": application.application_id
    }