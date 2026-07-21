import numpy as np
import pandas as pd
from typing import Dict


EMI_KEYWORDS = ["emi", "loan", "ecs", "nach", "autodebit"]
SALARY_KEYWORDS = ["salary", "payroll", "sal"]

MIN_TRANSACTIONS_REQUIRED = 3  

class BankFeatureEngineerError(Exception):
    """Raised when the input DataFrame is too sparse or malformed to trust."""
    pass


class BankFeatureEngineer:
    def __init__(self, df: pd.DataFrame):
        if df is None or df.empty:
            raise BankFeatureEngineerError("Empty bank dataframe — cannot engineer features.")

        self.df = df.copy()
        self._prepare()

    def _prepare(self):
        self.df["amount"] = (
            self.df["amount"].astype(str).str.replace(",", "", regex=False)
        )
        self.df["amount"] = pd.to_numeric(self.df["amount"], errors="coerce")

        self.df["type"] = self.df["type"].astype(str).str.upper().str.strip()

        self.df["date"] = pd.to_datetime(self.df["date"], errors="coerce", dayfirst=True)

        if "closing_balance" in self.df.columns:
            self.df["closing_balance"] = (
                self.df["closing_balance"].astype(str).str.replace(",", "", regex=False)
            )
            self.df["closing_balance"] = pd.to_numeric(self.df["closing_balance"], errors="coerce")

        self.df["narration"] = self.df["narration"].fillna("").astype(str)

        self.df = self.df.dropna(subset=["date", "amount"])

        if len(self.df) < MIN_TRANSACTIONS_REQUIRED:
            raise BankFeatureEngineerError(
                f"Only {len(self.df)} valid transaction rows after cleaning; "
                f"minimum required is {MIN_TRANSACTIONS_REQUIRED}."
            )

        self._cr_rows = self.df[self.df["type"] == "CR"]
        self._dr_rows = self.df[self.df["type"] == "DR"]
        self._clean_balance_df = self._clean_closing_balance(self.df)

    def _clean_closing_balance(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Drops closing_balance values that are implausible relative to the
        rest of the statement's balance distribution (MAD-based outlier
        detection) — guards against OCR/parsing artifacts corrupting a
        single row's balance while the rest of the statement is fine.
        """
        if "closing_balance" not in df.columns:
            return df

        balances = df["closing_balance"].dropna()
        if len(balances) < 5:
            return df

        median = balances.median()
        mad = (balances - median).abs().median()
        if mad == 0:
            return df

        modified_z = 0.6745 * (df["closing_balance"] - median).abs() / mad
        outlier_mask = modified_z > 10

        if outlier_mask.sum() > 0:
            print(
                f"[BankFeatureEngineer] Dropping {int(outlier_mask.sum())} "
                f"closing_balance outlier(s): {df.loc[outlier_mask, 'closing_balance'].tolist()}"
            )

        cleaned = df.copy()
        cleaned.loc[outlier_mask, "closing_balance"] = np.nan
        return cleaned

    def mean_monthly_credit(self):
        monthly = self._cr_rows.groupby(self._cr_rows["date"].dt.to_period("M"))["amount"].sum()
        return round(float(monthly.mean()), 2) if len(monthly) else None

    def cashflow_cv(self):
        monthly = self.df.groupby(self.df["date"].dt.to_period("M"))["amount"].sum()
        if len(monthly) < 2 or monthly.mean() == 0:
            return None
        return round(float(monthly.std() / monthly.mean()), 4)

    def min_balance_l3m(self):
        if "closing_balance" not in self.df.columns:
            return None
        df = self._clean_balance_df
        latest = df["date"].max()
        last_3m = df[df["date"] >= latest - pd.DateOffset(months=3)]
        valid = last_3m["closing_balance"].dropna()
        return round(float(valid.min()), 2) if len(valid) else None

    def credit_debit_ratio(self):
        total_credit = float(self._cr_rows["amount"].sum())
        total_debit = float(self._dr_rows["amount"].sum())

        print(f"[BankFeatureEngineer] CR={total_credit:.2f}  DR={total_debit:.2f}")

        if total_credit == 0 and total_debit == 0:
            return None

        if total_credit == 0:
            # No credits observed in this window — treat as missing data,
            # not as the worst-case ratio. Zero here likely means an
            # incomplete/partial statement, not zero income.
            return None

        if total_debit == 0:
            return 2.0  # conservative cap

        return round(total_credit / total_debit, 4)

    def salary_regularity_flag(self):
        mask = self._cr_rows["narration"].str.lower().str.contains(
            "|".join(SALARY_KEYWORDS), na=False
        )
        salary_txns = self._cr_rows[mask]
        if salary_txns.empty:
            return False
        return bool(salary_txns["date"].dt.to_period("M").nunique() >= 3)

    def emi_detection_flag(self):
        return True if self.df["narration"]\
        .str.lower()\
        .str.contains("|".join(EMI_KEYWORDS), na=False)\
        .any() else False

    def income_overstate_ratio(self):
        salary_mask = self._cr_rows["narration"].str.lower().str.contains(
            "|".join(SALARY_KEYWORDS), na=False
        )
        salary_total = float(self._cr_rows[salary_mask]["amount"].sum())
        all_credits = float(self._cr_rows["amount"].sum())
        if salary_total == 0:
            return None
        return round(all_credits / salary_total, 4)

    def build_features(self) -> Dict:
        # FIX: each feature method is now called exactly ONCE and stored in
        # a local variable, then reused for both the None-check and the
        # value. The original code called e.g. self.cashflow_cv() twice —
        # once in the `if` condition, once as the value — which duplicated
        # any side effects (credit_debit_ratio()'s print statement ran
        # twice per call) and would cause inconsistent results if any of
        # these methods were ever made non-deterministic.
        mean_monthly_credit = self.mean_monthly_credit()
        cashflow_cv = self.cashflow_cv()
        min_balance_l3m = self.min_balance_l3m()
        credit_debit_ratio = self.credit_debit_ratio()
        income_overstate_ratio = self.income_overstate_ratio()

        return {
            "mean_monthly_credit": (
                float(mean_monthly_credit) if mean_monthly_credit is not None else None
            ),
            "cashflow_cv": (
                float(cashflow_cv) if cashflow_cv is not None else None
            ),
            "min_balance_l3m": (
                float(min_balance_l3m) if min_balance_l3m is not None else None
            ),
            "credit_debit_ratio": (
                float(credit_debit_ratio) if credit_debit_ratio is not None else None
            ),
            "salary_regularity_flag": bool(self.salary_regularity_flag()),
            "emi_detection_flag": bool(self.emi_detection_flag()),
            "income_overstate_ratio": (
                float(income_overstate_ratio) if income_overstate_ratio is not None else None
            ),
        }