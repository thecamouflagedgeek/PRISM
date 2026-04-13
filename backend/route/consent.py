from fastapi import APIRouter
from pydantic import BaseModel
import uuid

router = APIRouter()

class ConsentRequest(BaseModel):
    user_id: str
    consent: bool

@router.post("/consent")
def consent(data: ConsentRequest):
    if not data.consent:
        return {"status": "blocked"}

    return {
        "session_id": str(uuid.uuid4()),
        "status": "consent_recorded"
    }