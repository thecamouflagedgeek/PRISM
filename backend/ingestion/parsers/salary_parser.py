from ingestion.parsers.base_parser import BaseParser
from ingestion.universal_pipeline import UniversalParser

class SalaryParser(BaseParser):
    def __init__(self, ocr_engine=None):
        self.universal_parser = UniversalParser(ocr_engine)

    def extract(self, file_path: str):
        pass

    def transform(self, data):
        pass

    def validate(self, df):
        pass
        
    def parse(self, file_path: str):
        # SalaryParser in assessment_routes.py uses .parse() instead of process_doc
        doc_type, mapped_data = self.universal_parser.process(file_path)
        if doc_type != "SALARY":
            raise ValueError(f"Expected SALARY document, but classified as {doc_type}")
        return mapped_data