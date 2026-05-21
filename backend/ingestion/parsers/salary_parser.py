import re
import pandas as pd
from ingestion.parsers.base_parser import BaseParser
from ingestion.utils.pdf_utils import extract_txt_pymupdf
from ingestion.utils.pdf_utils import extract_txt_pdfplumbr
from ingestion.utils.regex_utils import clean_amount

class SalaryParser(BaseParser):

    def extract(self, file_path):
        text = extract_txt_pdfplumbr(file_path)

        if len(text.strip()) < 50:
            text = extract_txt_pymupdf(file_path)

        return text

    def transform(self, text):

        data = {}

        patterns = {
            "gross_salary": r"Gross Salary\s*:?\s*([\d,]+\.\d+)",
            "net_salary": r"Net Salary\s*:?\s*([\d,]+\.\d+)",
            "pf": r"PF\s*:?\s*([\d,]+\.\d+)"
        }

        for field, pattern in patterns.items():

            match = re.search(pattern, text)

            if match:
                data[field] = clean_amount(match.group(1))

        return pd.DataFrame([data])

    def validate(self, df):
        required_columns = ["employee_name","gross_salary","net_salary"]
        missing = []
        for col in required_columns:
            if col not in df.columns:
                missing.append(col)
        return {"valid": len(missing) == 0,"missing_fields": missing}