import re
import pandas as pd
from ingestion.parsers.base_parser import BaseParser
from ingestion.utils.pdf_utils import extract_txt_pymupdf
from ingestion.utils.pdf_utils import extract_txt_pdfplumbr
from ingestion.utils.regex_utils import clean_amount

class UtilityParser(BaseParser):
    def extract(self, file_path):
        text = extract_txt_pdfplumbr(file_path)
        if len(text.strip()) < 50:
            text = extract_txt_pymupdf(file_path)
        return text

    def transform(self, text):
        data = {}
        amount_match = re.search(
            r"Bill Amount\s*:?\s*([\d,]+\.\d+)",
            text
)

        if amount_match:
            data["bill_amount"] = clean_amount(
                amount_match.group(1)
            )
        return pd.DataFrame([data])

    def validate(self, df):
        return True