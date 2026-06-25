from llm.extractor import extract_financial_data
from llm.schema import SalarySchema


class SalaryParser:

    def __init__(self, ocr):
        self.ocr = ocr

    def parse(self, file_path):

        text = self.ocr.extract_text(
            file_path
        )

        extracted = extract_financial_data(
            text
        )

        validated = SalarySchema(
            **extracted
        )

        return validated.model_dump()