from fastapi import APIRouter, UploadFile, File, Header, HTTPException, Depends
import tempfile
import os
from datetime import datetime
import pandas as pd
from core.session_store import get_session
from ingestion.parsers.bank_parser import BankParser
from ingestion.parsers.salary_parser import SalaryParser
from ingestion.parsers.utility_parser import UtilityParser
from services.ocr_service import get_ocr_engine
from features.bank_features import BankFeatureEngineer
from features.salary_features import SalaryFeatureEngineer
from features.utility_features import UtilityFeatureEngineer
from services.assessment_service import assess_borrower

import math
import numpy as np


router = APIRouter(
    prefix="/assess",
    tags=["Assessment"],
)


# ---------------------------------------------------------------------------
# TEMP FILE HANDLING
# ---------------------------------------------------------------------------

async def save_temp(file: UploadFile):
    if file is None:
        return None

    if not file.filename:
        return None

    contents = await file.read()

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf",
    )

    tmp.write(contents)
    tmp.close()

    return tmp.name


def assert_valid_path(path, name="file"):
    if not path:
        raise ValueError(
            f"{name} path is missing (None received)"
        )


# ---------------------------------------------------------------------------
# GENERIC DOCUMENT PROCESSING
# ---------------------------------------------------------------------------

def process_doc(parser, engineer_cls, path, ocr_engine=None):
    """
    Existing generic document processing flow.

    Preserves the original behaviour:
        parser.extract()
        parser.transform()
        parser.validate()
        feature engineering

    Returns only engineered features.
    """
    raw = parser.extract(path)
    df = parser.transform(raw)

    parser.validate(df)

    engineer = engineer_cls(df)
    features = engineer.build_features()

    return features


# ---------------------------------------------------------------------------
# BANK DOCUMENT PROCESSING
# ---------------------------------------------------------------------------

def process_bank_doc(path):
    """
    Process a bank document.

    Returns:
        bank_features
        bank_transactions

    bank_features:
        Engineered features used by the credit-risk model.

    bank_transactions:
        Canonical structured transaction DataFrame used by
        the fraud engine and document-intelligence layer.
    """

    parser = BankParser()

    raw = parser.extract(path)

    transactions = parser.transform(raw)

    parser.validate(transactions)

    features = BankFeatureEngineer(
        transactions
    ).build_features()

    return features, transactions


# ---------------------------------------------------------------------------
# UTILITY DOCUMENT PROCESSING
# ---------------------------------------------------------------------------

def process_utility_doc(path):
    """
    Process a utility document while preserving both:

        1. Engineered utility features
        2. Raw structured utility data

    The engineered features are used by the credit-risk model.

    The raw structured data is passed independently to the
    document-consistency layer.
    """

    parser = UtilityParser()

    raw = parser.extract(path)

    utility_data = parser.transform(raw)

    parser.validate(utility_data)

    features = UtilityFeatureEngineer(
        utility_data
    ).build_features()

    return features, utility_data


# ---------------------------------------------------------------------------
# JSON SERIALIZATION HELPERS
# ---------------------------------------------------------------------------

def clean_json(obj):
    """
    Recursively convert objects into JSON-safe values.
    """

    if isinstance(obj, dict):
        return {
            k: clean_json(v)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [
            clean_json(v)
            for v in obj
        ]

    if isinstance(obj, tuple):
        return [
            clean_json(v)
            for v in obj
        ]

    if isinstance(obj, pd.DataFrame):
        return clean_json(
            obj.to_dict(orient="records")
        )

    if isinstance(obj, pd.Series):
        return clean_json(
            obj.to_dict()
        )

    if isinstance(obj, np.generic):
        obj = obj.item()

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None

    return obj


def features_to_dict(features):
    """
    Convert feature-engineering outputs into JSON-safe dictionaries.
    """

    if features is None:
        return None

    if isinstance(features, dict):
        data = features

    elif hasattr(features, "model_dump"):
        # Pydantic v2
        data = features.model_dump()

    elif hasattr(features, "dict"):
        # Pydantic v1
        data = features.dict()

    elif hasattr(features, "to_dict"):
        data = features.to_dict()

    else:
        data = vars(features)

    return clean_json(data)


# ---------------------------------------------------------------------------
# ASSESSMENT ENDPOINT
# ---------------------------------------------------------------------------

@router.post("")
async def assess(
    bank_file: UploadFile = File(...),
    salary_file: UploadFile = File(None),
    utility_file: UploadFile = File(None),
    session_id: str = Header(...),
    ocr_engine=Depends(get_ocr_engine),
):
    """
    Run the complete PRISM assessment.

    Pipeline:

        Bank document
            ↓
        Bank features + transactions
            ↓
        Credit Risk + Fraud Risk + Document Risk

        Salary document
            ↓
        Salary features + raw salary data
            ↓
        Credit Risk + Document Risk

        Utility document
            ↓
        Utility features + raw utility data
            ↓
        Credit Risk + Document Risk
    """

    # -----------------------------------------------------------------------
    # SESSION / CONSENT
    # -----------------------------------------------------------------------

    session = get_session(session_id)

    if not session:
        raise HTTPException(
            401,
            "Invalid session",
        )

    if not session.consent_bank:
        raise HTTPException(
            403,
            "Bank consent required",
        )

    # -----------------------------------------------------------------------
    # INITIALIZE DOCUMENT DATA
    # -----------------------------------------------------------------------

    bank_features = None
    bank_transactions = None

    salary_features = None
    salary_data = None

    utility_features = None
    utility_data = None

    # -----------------------------------------------------------------------
    # BANK
    # -----------------------------------------------------------------------

    bank_path = await save_temp(bank_file)

    assert_valid_path(
        bank_path,
        "bank_file",
    )

    try:
        bank_features, bank_transactions = process_bank_doc(
            bank_path
        )

    finally:
        if os.path.exists(bank_path):
            os.remove(bank_path)

    # -----------------------------------------------------------------------
    # SALARY
    # -----------------------------------------------------------------------

    if salary_file and session.consent_salary:

        salary_path = await save_temp(
            salary_file
        )

        assert_valid_path(
            salary_path,
            "salary_file",
        )

        try:
            salary_parser = SalaryParser(
                ocr_engine
            )

            # Preserve raw structured salary data.
            salary_data = salary_parser.parse(
                salary_path
            )

            if (
                not salary_data
                or not isinstance(salary_data, dict)
            ):
                raise HTTPException(
                    422,
                    "Salary parsing failed",
                )

            # Existing credit feature engineering.
            engineer = SalaryFeatureEngineer(
                salary_data
            )

            salary_features = engineer.build_features()

        finally:
            if os.path.exists(salary_path):
                os.remove(salary_path)

    # -----------------------------------------------------------------------
    # UTILITY
    # -----------------------------------------------------------------------

    if utility_file and session.consent_utility:

        utility_path = await save_temp(
            utility_file
        )

        assert_valid_path(
            utility_path,
            "utility_file",
        )

        try:
            # Preserve BOTH:
            #   utility_features
            #   utility_data
            utility_features, utility_data = (
                process_utility_doc(
                    utility_path
                )
            )

        finally:
            if os.path.exists(utility_path):
                os.remove(utility_path)

    # -----------------------------------------------------------------------
    # ASSESSMENT
    # -----------------------------------------------------------------------

    result = assess_borrower(

        # ---------------------------------------------------------------
        # Existing engineered features
        # Used by the credit-risk scorecard.
        # ---------------------------------------------------------------

        bank=bank_features,
        salary=salary_features,
        utility=utility_features,

        # ---------------------------------------------------------------
        # Identity/history
        #
        # This upload-only endpoint currently does not have borrower
        # identity/history information.
        #
        # Do NOT use session_id as borrower identity.
        # ---------------------------------------------------------------

        application={},
        application_history=[],

        # ---------------------------------------------------------------
        # Existing fraud input
        # ---------------------------------------------------------------

        transactions=bank_transactions,

        # ---------------------------------------------------------------
        # Raw structured document inputs
        #
        # These are used ONLY by the document-consistency layer.
        # ---------------------------------------------------------------

        bank_document=bank_transactions,
        salary_document=salary_data,
        utility_document=utility_data,
    )

    # -----------------------------------------------------------------------
    # STORE ASSESSMENT
    # -----------------------------------------------------------------------

    session.assessment_result = result

    # -----------------------------------------------------------------------
    # RESPONSE
    # -----------------------------------------------------------------------

    response = {
        "status": "success",
        "assessed_at": datetime.utcnow().isoformat(),
        "session_id": session_id,

        **result,

        "features": {
            "bank": features_to_dict(
                bank_features
            ),
            "salary": features_to_dict(
                salary_features
            ),
            "utility": features_to_dict(
                utility_features
            ),
        },
    }

    # -----------------------------------------------------------------------
    # NaN DEBUG CHECK
    # -----------------------------------------------------------------------

    def find_nan(obj, path="root"):

        if isinstance(obj, dict):

            for key, value in obj.items():
                find_nan(
                    value,
                    f"{path}.{key}",
                )

        elif isinstance(obj, list):

            for index, value in enumerate(obj):
                find_nan(
                    value,
                    f"{path}[{index}]",
                )

        elif isinstance(obj, float):

            if math.isnan(obj):
                print(
                    "NaN found at:",
                    path,
                )

    find_nan(response)

    print(response)

    return response