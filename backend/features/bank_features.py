import pandas as pd
import numpy as np
import re
from typing import Dict

EMI_KEYWORDS = [
    "emi","loan","finance","home credit","bajaj","hdfc ergo","axis finance","emi payment","ecs","nach",
]

SALARY_KEYWORDS = [
    "salary","sal","payroll","wages","salary credit","salary transfer",
]
class BankFeatureEngineer:

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        if self.df.empty:
            raise ValueError("Validated bank dataframe is empty")
        self._prepare()

    def _prepare(self):

        self.df.columns = [c.lower() for c in self.df.columns]
        self.df["date"] = pd.to_datetime(
            self.df["date"],
            errors="coerce",
            dayfirst=True)
        self.df["amount"] = pd.to_numeric(
            self.df["amount"],
            errors="coerce")
        self.df["closing_balance"] = pd.to_numeric(
            self.df["closing_balance"],
            errors="coerce")
        self.df["type"] = (
            self.df["type"]
            .astype(str)
            .str.upper()
            .str.strip())
        self.df["narration"] = (
            self.df["narration"]
            .astype(str)
            .fillna("")
            .str.lower())

        self.df["month"] = self.df["date"].dt.to_period("M")

    def mean_monthly_credit(self) -> float:

        credits = self.df[self.df["type"] == "CR"]
        monthly_credit = (
            credits
            .groupby("month")["amount"]
            .sum())

        if monthly_credit.empty:
            return 0.0
        return round(float(monthly_credit.mean()), 2)

    def cashflow_cv(self) -> float:
        monthly_cashflow = (
            self.df
            .groupby("month")["amount"]
            .sum())

        if len(monthly_cashflow) < 2:
            return 0.0
        mean = monthly_cashflow.mean()
        std = monthly_cashflow.std()
        if mean == 0:
            return 0.0
        return round(float(std / mean), 4)

    def min_balance_l3m(self) -> float:

        latest_date = self.df["date"].max()

        last_3m = self.df[
            self.df["date"] >= latest_date - pd.DateOffset(months=3)]
        if last_3m.empty:
            return 0.0
        return round(float(last_3m["closing_balance"].min()), 2)

    def credit_debit_ratio(self) -> float:
        total_credit = self.df[
            self.df["type"] == "CR"
        ]["amount"].sum()
        total_debit = self.df[
            self.df["type"] == "DR"
        ]["amount"].sum()
        if total_debit == 0:
            return 0.0

        return round(float(total_credit / total_debit), 4)

    def salary_regularity_flag(self) -> bool:
        salary_txns = self.df[
            self.df["narration"].str.contains(
                "|".join(SALARY_KEYWORDS),
                na=False
            )
        ]

        if salary_txns.empty:
            return False
        months = salary_txns["month"].nunique()
        return months >= 3

    def emi_detection_flag(self) -> bool:
        emi_txns = self.df[
            self.df["narration"].str.contains(
                "|".join(EMI_KEYWORDS),
                na=False
            )
        ]
        return not emi_txns.empty

    def income_overstate_ratio(self) -> float:
        salary_credits = self.df[
            (self.df["type"] == "CR") &
            (
                self.df["narration"].str.contains(
                    "|".join(SALARY_KEYWORDS),
                    na=False
                )
            )
        ]

        all_credits = self.df[
            self.df["type"] == "CR"
        ]["amount"].sum()
        salary_total = salary_credits["amount"].sum()
        if salary_total == 0:
            return 0.0
        return round(float(all_credits / salary_total), 4)

    def build_features(self) -> Dict:
        return {
            "mean_monthly_credit":
                self.mean_monthly_credit(),

            "cashflow_cv":
                self.cashflow_cv(),

            "min_balance_l3m":
                self.min_balance_l3m(),

            "credit_debit_ratio":
                self.credit_debit_ratio(),

            "salary_regularity_flag":
                self.salary_regularity_flag(),

            "emi_detection_flag":
                self.emi_detection_flag(),

            "income_overstate_ratio":
                self.income_overstate_ratio(),
        }