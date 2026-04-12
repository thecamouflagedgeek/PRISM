from fastapi import APIRouter

router=APIRouter()
@router.post("/upload")
def upload(data: dict):
    return{
        "doc_id":"DOC123",
        "status":"Uploaded"
    }