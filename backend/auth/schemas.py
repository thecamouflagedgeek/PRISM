from pydantic import BaseModel, Field


class SignupRequest(BaseModel):

    phone_number: str = Field(
        ...,
        min_length=10,
        max_length=15
    )


class VerifyOTPRequest(BaseModel):

    phone_number: str = Field(
        ...,
        min_length=10,
        max_length=15
    )

    otp: str = Field(
        ...,
        min_length=6,
        max_length=6
    )