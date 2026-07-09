from fastapi import APIRouter, HTTPException

from auth.schemas import SignupRequest, VerifyOTPRequest
from auth.service import signup, verify

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/signup")
def signup_user(request: SignupRequest):

    try:
        return signup(request.phone_number)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/verify")
def verify_user(request: VerifyOTPRequest):

    result = verify(
        request.phone_number,
        request.otp
    )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=400,
            detail=result["message"]
        )

    return result