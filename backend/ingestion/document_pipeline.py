# ingestion/document_pipeline.py
"""
PRISM Master Document Pipeline
--------------------------------
Single entry point: inspect → classify → route to the correct extractor →
validate → return either a calibrated score (savings/current account) or
an explicit "insufficient calibration" response (credit card, and any
future document type without a fitted model).

This file intentionally refuses to force uncalibrated features through a
scorecard that was never fit for them — that produced misleadingly
confident scores earlier in this project's history and must not recur.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any

from ingestion.document.inspector import DocumentInspector, LayoutType
from ingestion.extractors.pdf_text import extract_digital_text
from ingestion.extractors.ocr import extract_scanned_text
from ingestion.document.classifier import is_credit_card_statement

from ingestion.extractors.table import parse_transaction_rows, build_transaction_df
from ingestion.validators.consistency_validator import validate_consistency
from features.bank_features import BankFeatureEngineer, BankFeatureEngineerError

from ingestion.extractors.credit_card_summary import extract_credit_card_summary
from ingestion.extractors.table import parse_credit_card_transactions
from features.credit_card_features import CreditCardFeatureEngineer

import pandas as pd


class DocumentProcessingError(Exception):
    def __init__(self, error_code: str, message: str, issues: Optional[list] = None):
        self.error_code = error_code
        self.message = message
        self.issues = issues or []
        super().__init__(message)


@dataclass
class PipelineResult:
    document_type: str          # "savings_account" | "credit_card" | "unknown"
    is_scoreable: bool          # True only if a calibrated model exists for this type
    features: Dict[str, Any]
    raw_summary: Dict[str, Any]


class DocumentPipeline:
    def __init__(self, ocr_engine=None):
        self.ocr_engine = ocr_engine
        self.inspector = DocumentInspector()

    def process(self, file_path: str, password: str = None) -> PipelineResult:
        inspection = self.inspector.inspect(file_path, password=password)

        try:
            if inspection.layout_type == LayoutType.UNREADABLE:
                raise DocumentProcessingError(
                    "document_unreadable",
                    "Document could not be opened — possibly corrupt, wrong password, or unsupported format."
                )

            if inspection.layout_type == LayoutType.DIGITAL:
                raw_text = extract_digital_text(inspection.readable_path)
            else:
                raw_text = extract_scanned_text(inspection.readable_path, self.ocr_engine)

            if not raw_text or not raw_text.strip():
                raise DocumentProcessingError(
                    "document_unreadable",
                    "No readable text could be extracted from this document, even after OCR."
                )

            if is_credit_card_statement(raw_text):
                return self._process_credit_card(raw_text)
            else:
                return self._process_savings_account(raw_text)

        finally:
            self.inspector.cleanup(inspection)

    def _process_savings_account(self, raw_text: str) -> PipelineResult:
        rows = parse_transaction_rows(raw_text)
        df = build_transaction_df(rows)

        result = validate_consistency(df, raw_text)
        if not result.passed:
            raise DocumentProcessingError(
                "extraction_consistency_failed",
                "Extracted data failed consistency checks against the statement's own summary.",
                issues=result.issues
            )

        try:
            engineer = BankFeatureEngineer(df)
            features = engineer.build_features()
        except BankFeatureEngineerError as e:
            raise DocumentProcessingError("feature_engineering_failed", str(e))

        return PipelineResult(
            document_type="savings_account",
            is_scoreable=True,   # calibrated WoE/LR scorecard exists for this type
            features=features,
            raw_summary=result.summary,
        )

    def _process_credit_card(self, raw_text: str) -> PipelineResult:
        rows = parse_credit_card_transactions(raw_text)
        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "narration", "amount", "type"])

        if df.empty:
            raise DocumentProcessingError(
                "credit_card_extraction_failed",
                "Could not extract any transactions from this credit card statement."
            )

        summary = extract_credit_card_summary(raw_text)
        engineer = CreditCardFeatureEngineer(df, summary)
        features = engineer.build_features()

        return PipelineResult(
            document_type="credit_card",
            is_scoreable=False,  # NO calibrated model exists yet — see note below
            features=features,
            raw_summary=summary,
        )