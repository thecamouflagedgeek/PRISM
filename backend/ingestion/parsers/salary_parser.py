from llm.extractor import extract_financial_data
from llm.schema import SalarySchema

class SalaryParser:

    def __init__(self, ocr_engine):
        self.ocr = ocr_engine

    def parse(self, file_path):

        text = self.ocr.extract_text(file_path)

        structured_data = extract_financial_data(text)

        return structured_data