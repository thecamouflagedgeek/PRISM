import pandas as pd
import pdfplumber
import re

from ingestion.parsers.base_parser import BaseParser
from ingestion.utils.pdf_utils import extract_txt_pymupdf
from ingestion.utils.regex_utils import clean_amount


class BankParser(BaseParser):

    #EXTRACT
    def extract(self, file_path: str):

        rows = []
        # pdfplumber extraction
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()

                if table:
                    for row in table:
                        rows.append(row)
        if len(rows) > 1:
            return pd.DataFrame(rows)

        # Fallback
        return self.extract_fallback(file_path)

    # PYMUPDF FALLBACK
    def extract_fallback(self, file_path):
        text = extract_txt_pymupdf(file_path)
        text = re.sub(r"\s+", " ", text)
        pattern = re.compile(
            r"("
            r"\d{2}[/-]\d{2}[/-]\d{2,4}"
            r")"
            r"(.*?)"
            r"([\d,]+\.\d{2})?"
            r"\s*"
            r"([\d,]+\.\d{2})?"
            r"\s*"
            r"([\d,]+\.\d{2})"
        )

        matches = pattern.findall(text)
        rows = []
        for match in matches:
            rows.append([
                match[0],   # date
                match[1],   # narration
                match[2],   # debit
                match[3],   # credit
                match[4]    # balance
            ])
        return pd.DataFrame(
            rows,
            columns=[
                "Date",
                "Narration",
                "Withdrawal Amt.",
                "Deposit Amt.",
                "Closing Balance"
            ]
        )
    def transform(self, df):

        if df.empty:
            return df
        if len(df.columns) >= 5:
            df.columns = df.iloc[0]
            df = df[1:]
            df = df.dropna(axis=1, how="all")
            df.columns = [
                str(col).replace("\n", " ").strip()
                for col in df.columns
            ]
        column_mapping = {
            "Date": "date",
            "Txn Date": "date",

            "Narration": "narration",
            "Description": "narration",

            "Withdrawal Amt.": "debit",
            "Withdrawal Amt": "debit",
            "Debit": "debit",

            "Deposit Amt.": "credit",
            "Deposit Amt": "credit",
            "Credit": "credit",

            "Closing Balance": "closing_balance",
            "Closing_Balance": "closing_balance",
            "Balance": "closing_balance"
        }

        df.rename(columns=column_mapping, inplace=True)
        for col in ["debit", "credit", "closing_balance"]:

            if col in df.columns:
                df[col] = df[col].apply(clean_amount)
        def detect_type(row):

            if pd.notna(row.get("credit")) and row.get("credit") > 0:
                return "CR"

            if pd.notna(row.get("debit")) and row.get("debit") > 0:
                return "DR"

            return None

        df["type"] = df.apply(detect_type, axis=1)
        final_df = pd.DataFrame()

        final_df["date"] = df.get("date")

        final_df["amount"] = (
            df.get("credit", pd.Series(0))
            .fillna(0)
            +
            df.get("debit", pd.Series(0))
            .fillna(0)
        )

        final_df["type"] = df["type"]
        final_df["narration"] = df.get("narration")
        final_df["closing_balance"] = df.get("closing_balance")

        return final_df.reset_index(drop=True)
    
    def validate(self, df):

        required_columns = [
            "date",
            "amount",
            "type",
            "narration",
            "closing_balance"
        ]

        for col in required_columns:

            if col not in df.columns:
                raise ValueError(
                    f"Missing standardized column: {col}"
                )

        return True