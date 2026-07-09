import random
from datetime import datetime, timedelta

from auth.store import otp_store


OTP_EXPIRY_MINUTES = 5


def generate_otp(phone_number: str):

    otp = str(random.randint(100000, 999999))

    expiry = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp_store[phone_number] = {
        "otp": otp,
        "expires_at": expiry
    }

    print("\n==============================")
    print("Generated OTP:", otp)
    print("Phone:", phone_number)
    print("==============================\n")

    return otp


def verify_otp(phone_number: str, entered_otp: str):

    record = otp_store.get(phone_number)

    if not record:
        return False

    if datetime.utcnow() > record["expires_at"]:
        del otp_store[phone_number]
        return False

    if record["otp"] != entered_otp:
        return False

    del otp_store[phone_number]

    return True