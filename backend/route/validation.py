from fastapi import APIRouter
from ingestion.process import process_input
router=APIRouter()
@router.post("/validate")
def validate(data:dict):
    return{
        "validated":True,
        "tamper_flag":False,
        "confidence":0.91
    }