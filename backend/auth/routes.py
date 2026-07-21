from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from auth.schemas import SignupRequest, VerifyOTPRequest
from auth.service import signup, verify
from database.db import get_db

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/signup")
def signup_user(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    try:
        return signup(
            db,
            request.phone_number
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.post("/verify")
def verify_user(
    request: VerifyOTPRequest,
    db: Session = Depends(get_db)
):

    result = verify(
        db,
        request.phone_number,
        request.otp
    )

    if result["status"] == "failed":
        raise HTTPException(
            status_code=400,
            detail=result["message"]
        )

    return result