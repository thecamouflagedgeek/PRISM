from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel
from scoring.rules import calculate_score
from fraud.checks import check_fraud
from explain.reasons import generate_reasons
from ingestion.process import process_input

router=APIRouter()
class Borrower(BaseModel):
    income:float
    expenses:float
    credit_score:int
    existing_loans:int

@router.post("/assess")
def assess_risk(data:Borrower):
    processed=process_input(data)
    score=calculate_score(processed)
    fraud=check_fraud(processed)
    reason=generate_reasons(processed)

    if score<0.3:
        level="LOW"
    elif score<0.6:
        level="MODERATE"
    else:
        level="HIGH"
    
    return{
        "risk_score":score,
        "risk_level":level,
        "fraud_flag":fraud,
        "reasons":reason
    }

