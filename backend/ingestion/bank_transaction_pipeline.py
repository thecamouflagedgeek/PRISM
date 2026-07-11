"""
Bank Transaction Pipeline
---------------------------
Orchestrates document inspection, extraction, and consistency validation
for bank statements specifically. This is the priority-1 slice: get a
correct, validated transaction DataFrame every time, before touching
feature engineering or scoring.
"""

from ingestion.document.inspector import DocumentInspector, LayoutType
from ingestion.extractors.pdf_text import extract_digital_text
from ingestion.extractors.ocr import extract_scanned_text
from ingestion.extractors.table import parse_transaction_rows, build_transaction_df
from ingestion.validators.consistency_validator import validate_consistency


class BankTransactionPipelineError(Exception):
    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Bank transaction extraction failed consistency checks: {issues}")


class BankTransactionPipeline:
    def __init__(self, ocr_engine=None):
        self.ocr_engine = ocr_engine
        self.inspector = DocumentInspector()

    def process(self, file_path: str, password: str = None):
        inspection = self.inspector.inspect(file_path, password=password)

        try:
            if inspection.layout_type == LayoutType.UNREADABLE:
                raise ValueError("Document could not be opened — possibly corrupt or wrong password.")

            if inspection.layout_type == LayoutType.DIGITAL:
                text = extract_digital_text(inspection.readable_path)
            else:
                text = extract_scanned_text(inspection.readable_path, self.ocr_engine)

            if not text or not text.strip():
                raise ValueError("Text extraction failed: NO READABLE CONTENT")

            # ---- DEBUG: dump raw extracted text ----
            print(">>> RAW STATEMENT TEXT (first 3000 chars):", flush=True)
            print(text[:3000], flush=True)
            print(">>> TOTAL LINES:", len(text.split("\n")), flush=True)
            print(">>> FIRST 60 LINES:", flush=True)
            for i, line in enumerate(text.split("\n")[:60]):
                print(f"  [{i}] {repr(line)}", flush=True)
            # ---- END DEBUG ----

            rows = parse_transaction_rows(text)
            df = build_transaction_df(rows)

            result = validate_consistency(df, text)
            if not result.passed:
                raise BankTransactionPipelineError(result.issues)

            return df, text, result.summary

        finally:
            self.inspector.cleanup(inspection)