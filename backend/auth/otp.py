import logging
import os
import secrets
from datetime import datetime, timedelta

from auth.store import otp_store


OTP_EXPIRY_MINUTES = 5
logger = logging.getLogger(__name__)


def local_otp_logging_enabled() -> bool:
    """Allow OTP console delivery only in explicitly opted-in local development."""
    return (
        os.getenv("PRISM_ENV", "").strip().lower() == "development"
        and os.getenv("PRISM_OTP_LOGGING", "").strip().lower() == "true"
        and not os.getenv("PYTEST_CURRENT_TEST")
    )


def generate_otp(phone_number: str):
    otp = str(secrets.randbelow(900000) + 100000)

    expiry = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp_store[phone_number] = {
        "otp": otp,
        "expires_at": expiry
    }

    if local_otp_logging_enabled():
        logger.warning("DEVELOPMENT-ONLY OTP: %s", otp)

    return otp


def verify_otp(phone_number: str, entered_otp: str):

    record = otp_store.get(phone_number)

    if not record:
        return False

    if datetime.utcnow() > record["expires_at"]:
        del otp_store[phone_number]
        return False

    if not isinstance(entered_otp, str) or not secrets.compare_digest(record["otp"], entered_otp):
        return False

    del otp_store[phone_number]

    return True
