from ingestion.parsers.base_parser import BaseParser
from ingestion.universal_pipeline import UniversalParser
import pandas as pd


class ExtractionQualityError(Exception):
    """Raised when extracted utility data fails plausibility checks and should not be scored."""
    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Utility extraction quality insufficient: {issues}")


class UtilityParser(BaseParser):
    def __init__(self, ocr_engine=None):
        self.universal_parser = UniversalParser(ocr_engine)

    def extract(self, file_path: str, password: str = None):
        doc_type, mapped_data, raw_text = self.universal_parser.process(file_path, password=password)

        if doc_type != "UTILITY":
            raise ValueError(f"Expected UTILITY document, but classified as {doc_type}")

        self._validate_extraction_quality(mapped_data)

        return mapped_data

    def _validate_extraction_quality(self, data):
        """
        Mirrors the bank/salary quality gates: refuse to let extraction with
        no usable bill data reach the feature engineer and produce a
        misleadingly confident output.
        """
        issues = []

        if data is None:
            issues.append("No utility data extracted at all.")
        elif isinstance(data, pd.DataFrame):
            if data.empty:
                issues.append("Utility extraction returned an empty result.")
            else:
                row = data.iloc[0].to_dict()
                if not row.get("bill_amount"):
                    issues.append("bill_amount could not be extracted from this document.")
        elif isinstance(data, dict):
            if not data:
                issues.append("Utility extraction returned an empty result.")
            elif not data.get("bill_amount"):
                issues.append("bill_amount could not be extracted from this document.")
        else:
            issues.append(f"Unexpected data type from extractor: {type(data)}")

        if issues:
            raise ExtractionQualityError(issues)

    def transform(self, data):
        """
        Converts the DataFrame produced by UtilityExtractor into a plain dict,
        matching the pattern used for SalaryParser — UtilityFeatureEngineer
        should receive consistent dict-style access, not a DataFrame.
        """
        if data is None:
            return {}

        if isinstance(data, dict):
            return data

        if isinstance(data, pd.DataFrame):
            if data.empty:
                return {}
            return data.iloc[0].to_dict()

        return data

    def validate(self, data) -> bool:
        # Structural validation already performed by ValidationPipeline in
        # UniversalParser, plus the quality gate in extract(). This hook
        # stays for interface compatibility with process_doc().
        return True