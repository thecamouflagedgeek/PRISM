from fastapi import APIRouter, Request, HTTPException
from ingestion.parsers.bank_parser import BankParser 
from ingestion.parsers.salary_parser import SalaryParser
from ingestion.parsers.utility_parser import UtilityParser
from utils.text_extractor import extract_text
from scoring.risk_scorer import compute_risk_score

router = APIRouter()

@router.post("/assess")
async def assess(request: Request):
    try:
        data = await request.json()

        documents = data.get("documents", [])

        bank_features = None
        salary_features = None
        utility_features = None

        for doc in documents:

            doc_type = doc.get("document_type", "").lower()
            text = doc.get("text", "")

            if doc_type == "bank":
                bank_features =BankParser(text)

            elif doc_type == "salary":
                salary_features = SalaryParser(text)

            elif doc_type == "utility":
                utility_features = UtilityParser(text)

        result = compute_risk_score(
            bank_features,
            salary_features,
            utility_features
        )

        return {
            "status": "success",
            **result
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )