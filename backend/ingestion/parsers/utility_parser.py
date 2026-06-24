import re
import pandas as pd

from ingestion.parsers.base_parser import BaseParser
from ingestion.utils.pdf_utils import (
    extract_txt_pdfplumber,
    extract_txt_pymupdf
)


class UtilityParser(BaseParser):

    def extract(self, file_path: str):

        text = extract_txt_pdfplumber(
            file_path
        )

        if not text or len(text.strip()) < 50:

            text = extract_txt_pymupdf(
                file_path
            )

        return text

    def transform(self, text: str):

        utility_data = {}

        lines = [

            line.strip()

            for line in text.split("\n")

            if line.strip()
        ]

        ignore_words = [

            "bill",
            "invoice",
            "statement",
            "account",
            "customer",
            "payment",
            "charges",
            "electricity",
            "water",
            "gas",
            "utility"
        ]

        candidates = []

        for line in lines[:20]:

            if len(line) < 5:
                continue

            if re.search(r"\d", line):
                continue

            lower = line.lower()

            if any(
                word in lower
                for word in ignore_words
            ):
                continue

            candidates.append(line)

        utility_data["provider"] = (

            max(
                candidates,
                key=len
            )

            if candidates

            else None
        )

        bill_match = re.search(

            r"Bill\s*date[: ]*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",

            text,

            re.IGNORECASE
        )

        utility_data["bill_date"] = (

            bill_match.group(1)

            if bill_match

            else None
        )

        period_match = re.search(

            r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s*[-–]\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

            text,

            re.IGNORECASE
        )

        if period_match:

            utility_data["billing_period"] = (

                period_match.group(1)

                + " - " +

                period_match.group(2)
            )

        else:

            utility_data["billing_period"] = None

        due_match = re.search(

            r"pay\s*(?:this\s*)?by\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",

            text,

            re.IGNORECASE
        )

        utility_data["due_date"] = (

            due_match.group(1)

            if due_match

            else None
        )

        def extract_float(pattern):

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                try:

                    return float(
                        match.group(1)
                    )

                except:

                    return None

            return None

        utility_data["electricity_charges"] = extract_float(

            r"Electricity\s*charges\s*£?([\d\.]+)"
        )

        utility_data["standing_charge"] = extract_float(

            r"Standing\s*charge\s*£?([\d\.]+)"
        )

        utility_data["vat"] = extract_float(

            r"VAT\s*£?([\d\.]+)"
        )

        utility_data["total_amount_due"] = extract_float(

            r"Total\s*amount\s*now\s*due\s*£?([\d\.]+)"
        )

        fields_found = sum(

            value is not None

            for value in utility_data.values()
        )

        utility_data["bill_confidence_score"] = round(

            fields_found / 7,

            2
        )

        utility_data["payment_consistency_score"] = 1

        utility_data["has_late_payment_flag"] = False

        return pd.DataFrame([
            {
                "bill_amount":
                    utility_data["total_amount_due"],

                "on_time_flag":
                    not utility_data["has_late_payment_flag"],

                "provider":
                    utility_data["provider"],

                "bill_date":
                    utility_data["bill_date"],

                "billing_period":
                    utility_data["billing_period"],

                "due_date":
                    utility_data["due_date"],

                "electricity_charges":
                    utility_data["electricity_charges"],

                "standing_charge":
                    utility_data["standing_charge"],

                "vat":
                    utility_data["vat"],

                "bill_confidence_score":
                    utility_data["bill_confidence_score"]
            }
        ])

    def validate(self, df):

        if df is None or df.empty:

            raise ValueError(
                "Utility dataframe is empty"
            )

        return True