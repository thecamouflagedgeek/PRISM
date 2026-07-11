# features/credit_card_features.py
import pandas as pd

class CreditCardFeatureEngineer:
    def __init__(self, transactions_df: pd.DataFrame, summary: dict):
        self.df = transactions_df
        self.summary = summary

    def credit_utilization(self) -> float:
        limit = self.summary.get("credit_limit")
        due = self.summary.get("total_amount_due")
        if not limit or limit == 0 or due is None:
            return None
        return round(due / limit, 4)

    def payment_behavior_flag(self) -> str:
        """
        'full' if payments/credits >= opening balance (paid in full),
        'minimum' if payments cover only the minimum due,
        'partial' otherwise, 'none' if no payment recorded.
        """
        paid = self.summary.get("payments_credits")
        opening = self.summary.get("opening_balance")
        minimum = self.summary.get("minimum_amount_due")

        if paid is None or paid == 0:
            return "none"
        if opening and paid >= opening:
            return "full"
        if minimum and paid <= minimum * 1.1:
            return "minimum"
        return "partial"

    def finance_charges_flag(self) -> bool:
        return self.df["narration"].str.contains("finance charge", case=False, na=False).any()

    def total_purchases(self) -> float:
        return round(float(self.df[self.df["type"] == "DR"]["amount"].sum()), 2)

    def total_payments(self) -> float:
        return round(float(self.df[self.df["type"] == "CR"]["amount"].sum()), 2)

    def build_features(self) -> dict:
        return {
            "credit_utilization": self.credit_utilization(),
            "payment_behavior_flag": self.payment_behavior_flag(),
            "finance_charges_flag": self.finance_charges_flag(),
            "total_purchases": self.total_purchases(),
            "total_payments": self.total_payments(),
        }