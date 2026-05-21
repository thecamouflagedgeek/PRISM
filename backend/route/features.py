from fastapi import APIRouter, UploadFile, File
import pandas as pd
import tempfile
import os
from ingestion.process import process_document
from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer

router = APIRouter()


# BANK FEATURES

@router.post("/features/bank")
async def generate_bank_features(
    file: UploadFile = File(...)
):
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as temp:

        temp.write(await file.read())
        temp_path = temp.name

    try:
        validated_df = process_document(temp_path,"bank")
        engineer = BankFeatureEngineer(validated_df)
        features = engineer.build_features()
        return {
            "status": "success",
            "document_type": "bank_statement",
            "features": features
        }

    finally:
        os.remove(temp_path)


# SALARY FEATURES

@router.post("/features/salary")
async def generate_salary_features(
    file: UploadFile = File(...)
):

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as temp:
        temp.write(await file.read())
        temp_path = temp.name

    try:
        validated_df = process_document(
            temp_path,
            "salary"
        )
        engineer = SalaryFeatureEngineer(
            validated_df
        )
        features = engineer.build_features()
        return {
            "status": "success",
            "document_type": "salary_slip",
            "features": features
        }

    finally:
        os.remove(temp_path)


# UTILITY FEATURES

@router.post("/features/utility")
async def generate_utility_features(
    file: UploadFile = File(...)
):
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as temp:
        temp.write(await file.read())
        temp_path = temp.name

    try:
        validated_df = process_document(temp_path, "utility")
        engineer = UtilityFeatureEngineer( validated_df)

        features = engineer.build_features()
        return {
            "status": "success",
            "document_type": "utility_bill",
            "features": features
        }
    finally:
        os.remove(temp_path)