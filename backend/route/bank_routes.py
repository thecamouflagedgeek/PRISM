from fastapi import APIRouter, UploadFile, File
import shutil
import os
from validation.runner import validate_dataframe
from validation.config import CONFIG
from ingestion.process import process_document

router = APIRouter()
UPLOAD_DIR = "temp"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/parse/bank")
async def parse_bank_statement(
    file: UploadFile = File(...)
):

    temp_path = os.path.join(UPLOAD_DIR,file.filename)
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    df = process_document(temp_path,"bank")
    validated_df = validate_dataframe(df,CONFIG["bank_fields"],"bank")
    return {
    "status": "success",
    "document_type": "bank_statement",
    "rows_extracted": len(validated_df),
    "data": validated_df.to_dict(orient="records")}