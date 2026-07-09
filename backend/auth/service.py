from auth.otp import generate_otp, verify_otp
from auth.store import verified_users

from core.session_store import create_session


def signup(phone_number: str):

    generate_otp(phone_number)

    return {
        "status": "success",
        "message": "OTP sent successfully"
    }


def verify(phone_number: str, otp: str):

    if not verify_otp(phone_number, otp):

        return {
            "status": "failed",
            "message": "Invalid or expired OTP"
        }

    verified_users[phone_number] = True

    session = create_session(phone_number)

    return {
        "status": "success",
        "message": "OTP verified",
        "session_id": session.session_id
    }