from fastapi import APIRouter
import uuid

#Complinace Layer
router=APIRouter()
@router.get("/consent")
def consent(data:dict):
    if not data.get("consent"):
        return {"status":"Blocked"}
    
    return{
        "session_id": str(uuid.uuid4()),
        "status":"Consent Given"
    }