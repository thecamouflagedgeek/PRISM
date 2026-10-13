from ingestion.parsers.base_parser import BaseParser
from ingestion.universal_pipeline import UniversalParser

class UtilityParser(BaseParser):
    def __init__(self, ocr_engine=None):
        self.universal_parser = UniversalParser(ocr_engine)
        self.metadata = {}

    def extract(self, file_path: str, password: str = None):
        doc_type, mapped_data = self.universal_parser.process(file_path, password=password)
        self.metadata = dict(self.universal_parser.last_metadata)
        if doc_type != "UTILITY":
            raise ValueError(f"Expected UTILITY document, but classified as {doc_type}")
        return mapped_data

    def transform(self, data):
        return data

    def validate(self, df):
        return True
