from fastapi import APIRouter, UploadFile, File
import shutil
import os

from ingestion.process import process_document

router = APIRouter()

UPLOAD_DIR = "temp"

os.makedirs(UPLOAD_DIR, exist_ok=True)
@router.post("/parse/salary")
async def parse_salary_slip(file: UploadFile = File(...)):

    temp_path = f"temp_{file.filename}"

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:

        df = process_document(temp_path, "salary")

        if df is None or df.empty:

            return {
                "status": "failed",
                "document_type": "salary_slip",
                "message": "No structured salary data extracted",
                "data": []
            }

        return {
            "status": "success",
            "document_type": "salary_slip",
            "rows_extracted": len(df),
            "data": df.to_dict(orient="records")
        }

    except Exception as e:

        return {
            "status": "error",
            "document_type": "salary_slip",
            "message": str(e)
        }