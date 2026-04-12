from fastapi import APIRouter

router = APIRouter()

@router.get("/dashboard/{session_id}")
def dashboard(session_id: str):
    return {
        "score": 645,
        "risk_tier": "medium",
        "fraud_flag": False,
        "confidence": 0.79
    }