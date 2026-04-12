from fastapi import APIRouter

router = APIRouter()

@router.post("/get-explanation")
def explain(data: dict):
    return {
        "top_positive": ["employment_months"],
        "top_negative": ["transaction_volatility"],
        "what_if": {"income_consistency": "+40 score"}
    }