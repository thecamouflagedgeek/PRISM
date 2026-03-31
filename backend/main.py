from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI()

# Request Model
class Borrower(BaseModel):
    income: float
    expenses: float
    credit_score: int
    existing_loans: int

# Response Model (optional but clean)
class RiskResponse(BaseModel):
    risk_score: float
    risk_level: str
    fraud_flag: str
    reasons: List[str]


def calculate_risk(data: Borrower):
    income = data.income
    expenses = data.expenses
    credit_score = data.credit_score
    loans = data.existing_loans

    reasons = []
    risk_score = 0

    # Rule 1: Expense Ratio
    if expenses > income * 0.7:
        risk_score += 0.3
        reasons.append("High expense to income ratio")

    # Rule 2: Credit Score
    if credit_score < 600:
        risk_score += 0.4
        reasons.append("Low credit score")
    elif credit_score < 700:
        risk_score += 0.2
        reasons.append("Moderate credit score")

    # Rule 3: Existing Loans
    if loans > 3:
        risk_score += 0.3
        reasons.append("Too many existing loans")
    elif loans > 1:
        risk_score += 0.1
        reasons.append("Multiple existing loans")

    # Fraud Flag
    fraud_flag = "Low"
    if income == 0 or credit_score == 0:
        fraud_flag = "High"
        reasons.append("Suspicious or missing data")

    # Risk Level
    if risk_score < 0.3:
        risk_level = "Low"
    elif risk_score < 0.6:
        risk_level = "Medium"
    else:
        risk_level = "High"

    return {
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "fraud_flag": fraud_flag,
        "reasons": reasons
    }


@app.post("/assess-risk", response_model=RiskResponse)
def assess_risk(data: Borrower):
    return calculate_risk(data)