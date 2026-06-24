import pandas as pd
import pdfplumber
import re

from ingestion.parsers.base_parser import BaseParser
from ingestion.utils.pdf_utils import extract_txt_pymupdf
from ingestion.utils.regex_utils import clean_amount


class BankParser(BaseParser):

    def extract(self, file_path: str):

        rows = []

        try:
            with pdfplumber.open(file_path) as pdf:

                for page in pdf.pages:

                    tables = page.extract_tables()

                    if tables:

                        for table in tables:

                            for row in table:

                                if row:
                                    rows.append(row)

        except Exception:
            pass

        if rows:
            return pd.DataFrame(rows)

        return self.extract_fallback(file_path)

    def extract_fallback(self, file_path):

        text = extract_txt_pymupdf(file_path)

        lines = text.split("\n")

        rows = []

        date_pattern = re.compile(
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
        )

        amount_pattern = re.compile(
            r"[\d,]+\.\d{2}"
        )

        for line in lines:

            if not date_pattern.search(line):
                continue

            amounts = amount_pattern.findall(line)

            if len(amounts) < 1:
                continue

            date_match = date_pattern.search(line)

            date = date_match.group()

            narration = line.replace(date, "").strip()

            debit = None
            credit = None
            balance = None

            if len(amounts) >= 1:
                balance = amounts[-1]

            if len(amounts) >= 2:
                debit = amounts[-2]

            rows.append([
                date,
                narration,
                debit,
                credit,
                balance
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

        print("\nRAW DATA")
        print(df.head())

        if df.empty:

            return pd.DataFrame(
                columns=[
                    "date",
                    "amount",
                    "type",
                    "narration",
                    "closing_balance"
                ]
            )

        df.columns = [
            str(col).replace("\n", " ").strip()
            for col in df.columns
        ]

        possible_columns = {}

        for col in df.columns:

            lower = str(col).lower()

            if "date" in lower:
                possible_columns[col] = "date"

            elif (
                "narration" in lower
                or "description" in lower
                or "particular" in lower
            ):
                possible_columns[col] = "narration"

            elif (
                "withdrawal" in lower
                or "debit" in lower
            ):
                possible_columns[col] = "debit"

            elif (
                "deposit" in lower
                or "credit" in lower
            ):
                possible_columns[col] = "credit"

            elif (
                "balance" in lower
            ):
                possible_columns[col] = "closing_balance"

        df = df.rename(columns=possible_columns)

        for col in [
            "debit",
            "credit",
            "closing_balance"
        ]:

            if col in df.columns:

                df[col] = df[col].apply(
                    clean_amount
                )

        def detect_type(row):

            credit = row.get("credit")
            debit = row.get("debit")

            if pd.notna(credit) and credit > 0:
                return "CR"

            if pd.notna(debit) and debit > 0:
                return "DR"

            return None

        df["type"] = df.apply(
            detect_type,
            axis=1
        )

        final_df = pd.DataFrame()

        final_df["date"] = df.get("date")

        final_df["amount"] = (
            df.get(
                "credit",
                pd.Series(dtype=float)
            ).fillna(0)
            +
            df.get(
                "debit",
                pd.Series(dtype=float)
            ).fillna(0)
        )

        final_df["type"] = df["type"]

        final_df["narration"] = df.get(
            "narration"
        )

        final_df["closing_balance"] = df.get(
            "closing_balance"
        )

        final_df = final_df.dropna(
            subset=["date"]
        )

        print("\nTRANSFORMED DF")
        print(final_df.head())

        return final_df.reset_index(drop=True)

    def validate(self, df):

        if df.empty:
            raise ValueError(
                "No bank transactions extracted"
            )

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