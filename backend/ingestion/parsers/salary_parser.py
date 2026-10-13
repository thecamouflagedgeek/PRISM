from llm.extractor import extract_financial_data
from llm.schema import SalarySchema

class SalaryParser:

    def __init__(self, ocr_engine):
        self.ocr = ocr_engine
        self.metadata = {}

    def parse(self, file_path, password=None):

        if hasattr(self.ocr, "extract_text_with_metadata"):
            try:
                text, confidence = self.ocr.extract_text_with_metadata(file_path, password=password)
            except TypeError:
                text, confidence = self.ocr.extract_text_with_metadata(file_path)
        else:
            try:
                text = self.ocr.extract_text(file_path, password=password)
            except TypeError:
                text = self.ocr.extract_text(file_path)
            confidence = None
        self.metadata = {"method": "ocr_or_native_text", "text_length": len(text or ""),
                         "extraction_confidence": float(confidence) if confidence is not None else 0.0}

        structured_data = extract_financial_data(text)

        return structured_data
