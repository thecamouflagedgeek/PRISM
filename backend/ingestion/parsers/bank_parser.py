from ingestion.parsers.base_parser import BaseParser
from ingestion.universal_pipeline import UniversalParser

class BankParser(BaseParser):
    def __init__(self, ocr_engine=None):
        self.universal_parser = UniversalParser(ocr_engine)

    def extract(self, file_path: str):
        # We process everything in transform to respect the base_parser interface,
        # or we just process it here and pass the df to transform.
        doc_type, mapped_data = self.universal_parser.process(file_path)
        if doc_type != "BANK":
            raise ValueError(f"Expected BANK document, but classified as {doc_type}")
        return mapped_data

    def transform(self, data):
        # The universal pipeline already mapped it to the canonical schema
        return data

    def validate(self, df):
        # Validation was already performed by ValidationPipeline in UniversalParser
        return True