"""
Bank Transaction Pipeline

Responsible for:
1. Inspecting the uploaded document
2. Choosing the extraction strategy
3. Extracting text
4. Parsing transaction rows
5. Building canonical DataFrame
6. Validating consistency
"""

from ingestion.document.inspector import DocumentInspector, LayoutType

from ingestion.extractors.pdf_text import extract_digital_text
from ingestion.extractors.ocr import extract_scanned_text

from ingestion.extractors.table import (
    parse_transaction_rows,
    build_transaction_df,
)

from ingestion.validators.consistency_validator import validate_consistency


class BankTransactionPipelineError(Exception):
    def __init__(self, issues):
        self.issues = issues
        super().__init__(
            f"Bank transaction extraction failed consistency checks: {issues}"
        )


class BankTransactionPipeline:

    def __init__(self, ocr_engine=None):
        self.ocr_engine = ocr_engine
        self.inspector = DocumentInspector()

    def process(self, file_path: str, password: str = None):

        inspection = self.inspector.inspect(
            file_path,
            password=password
        )

        try:

            print("\n" + "=" * 100)
            print("PRISM BANK TRANSACTION PIPELINE")
            print("=" * 100)

            print("Layout Type :", inspection.layout_type)

            if inspection.layout_type == LayoutType.UNREADABLE:
                raise ValueError(
                    "Document could not be opened (wrong password or corrupt PDF)."
                )

            #############################################################
            # TEXT EXTRACTION
            #############################################################

            if inspection.layout_type == LayoutType.DIGITAL:

                print("\nExtraction Engine : DIGITAL (PyMuPDF/pdfplumber)")

                text = extract_digital_text(
                    inspection.readable_path
                )

            else:

                print("\nExtraction Engine : OCR")

                text = extract_scanned_text(
                    inspection.readable_path,
                    self.ocr_engine
                )

            if not text or not text.strip():
                raise ValueError(
                    "Text extraction failed: NO READABLE CONTENT"
                )

            #############################################################
            # RAW TEXT DEBUG
            #############################################################

            print("\n" + "=" * 100)
            print("RAW TEXT (FIRST 3000 CHARS)")
            print("=" * 100)

            print(text[:3000])

            print("\nTotal Characters :", len(text))
            print("Total Lines      :", len(text.splitlines()))

            #############################################################
            # ROW PARSING
            #############################################################

            rows = parse_transaction_rows(text)

            print("\n" + "=" * 100)
            print("PARSED ROWS")
            print("=" * 100)

            print("Rows Parsed :", len(rows))

            for idx, row in enumerate(rows[:20]):
                print(f"{idx+1}. {row}")

            #############################################################
            # DATAFRAME
            #############################################################

            df = build_transaction_df(rows)
            print(df[["amount", "type"]].tail(20))
            print(df["type"].value_counts())
            print(df.tail(20).to_string())
            print("\n" + "=" * 100)
            print("CANONICAL DATAFRAME")
            print("=" * 100)

            print(df.head(30))

            print("\nColumns")
            print(df.columns.tolist())

            print("\nData Types")
            print(df.dtypes)

            #############################################################
            # BALANCE DEBUG
            #############################################################

            if "closing_balance" in df.columns:

                print("\n" + "=" * 100)
                print("BALANCE COLUMN")
                print("=" * 100)

                print(df["closing_balance"].tail(20))

                print(
                    "\nFinal Extracted Balance :",
                    df.iloc[-1]["closing_balance"]
                )

            #############################################################
            # CREDIT / DEBIT DEBUG
            #############################################################

            if "type" in df.columns and "amount" in df.columns:

                cr = df.loc[
                    df["type"].astype(str).str.upper() == "CR",
                    "amount",
                ].sum()

                dr = df.loc[
                    df["type"].astype(str).str.upper() == "DR",
                    "amount",
                ].sum()

                print("\nCredit Total :", cr)
                print("Debit Total  :", dr)

            #############################################################
            # VALIDATION
            #############################################################

            result = validate_consistency(
                df,
                text,
            )

            print("\n" + "=" * 100)
            print("CONSISTENCY VALIDATION")
            print("=" * 100)

            print("Passed :", result.passed)

            print("Summary :")
            print(result.summary)

            if hasattr(result, "issues"):

                print("\nIssues")

                for issue in result.issues:
                    print("-", issue)

            #############################################################
            # FAIL
            #############################################################

            if not result.passed:

                raise BankTransactionPipelineError(
                    result.issues
                )

            #############################################################
            # SUCCESS
            #############################################################

            print("\n" + "=" * 100)
            print("PIPELINE COMPLETED SUCCESSFULLY")
            print("=" * 100)

            return (
                df,
                text,
                result.summary,
            )

        finally:

            self.inspector.cleanup(
                inspection
            )