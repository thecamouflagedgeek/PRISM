from fastapi import APIRouter

router = APIRouter()

@router.post("/fraud")
def fraud(data: dict):
    features = data.get("features")
    if features.get("loan_count_30d", 1) > 3:
        return {
            "fraud_flag": True,
            "fraud_score": 0.9,
            "reasons": ["loan_stacking"]
        }

    return {
        "fraud_flag": False,
        "fraud_score": 0.1,
        "reasons": []
    }