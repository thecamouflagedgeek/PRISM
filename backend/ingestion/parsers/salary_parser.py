from ingestion.parsers.base_parser import BaseParser
from ingestion.universal_pipeline import UniversalParser
import pandas as pd


class SalaryParsingError(Exception):
    """Raised when salary extraction produces no usable data."""
    pass


class SalaryParser(BaseParser):
    def __init__(self, ocr_engine=None):
        self.universal_parser = UniversalParser(ocr_engine)

    def extract(self, file_path: str, password: str = None):
        doc_type, mapped_data, raw_text = self.universal_parser.process(file_path, password=password)

        if doc_type != "SALARY":
            raise ValueError(f"Expected SALARY document, but classified as {doc_type}")

        return mapped_data

    def transform(self, data):
        """
        Converts the DataFrame produced by SalaryExtractor into a plain dict,
        since SalaryFeatureEngineer expects dict-style access, not a DataFrame.
        SalaryExtractor always returns a single-row DataFrame (one row of
        entities per document) or an empty DataFrame if nothing was found.
        """
        if data is None:
            return {}

        if isinstance(data, dict):
            return data

        if isinstance(data, pd.DataFrame):
            if data.empty:
                return {}
            # Single-row DataFrame → dict of column: value
            return data.iloc[0].to_dict()

        raise SalaryParsingError(f"Unexpected data type from extractor: {type(data)}")

    def validate(self, salary_dict: dict) -> None:
        if not salary_dict:
            raise SalaryParsingError("No salary entities extracted from document.")

        if not salary_dict.get("net_salary") and not salary_dict.get("gross_salary"):
            raise SalaryParsingError(
                "Neither net_salary nor gross_salary could be extracted. "
                "Document may not be a valid salary slip."
            )

    def parse(self, file_path: str, password: str = None) -> dict:
        """
        Public entry point used by the router: extract → transform → validate,
        returning a plain dict ready for SalaryFeatureEngineer.
        """
        raw = self.extract(file_path, password=password)
        salary_dict = self.transform(raw)
        self.validate(salary_dict)
        return salary_dict