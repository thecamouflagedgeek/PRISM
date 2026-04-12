from fastapi import APIRouter

router = APIRouter()

@router.post("/generate-score")
def score(data: dict):
    return {
        "score": 645,
        "risk_tier": "medium",
        "confidence": 0.79
    }