import pandas as pd
from typing import Dict
import numpy as np
class UtilityFeatureEngineer:

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        if self.df.empty:
            raise ValueError("Validated utility dataframe is empty")
        self.df.columns = [c.lower() for c in self.df.columns]

    # Average bill amount
    def avg_bill_amount(self):
        amounts = pd.to_numeric(self.df.get("bill_amount"),errors="coerce")
        if amounts.isna().all():
            return None

        return round(float(amounts.mean()), 2)

    # Maximum bill amount
    def max_bill_amount(self):

        amounts = pd.to_numeric(self.df.get("bill_amount"),errors="coerce")
        if amounts.isna().all():
            return None

        return round(float(amounts.max()), 2)

    # Payment discipline flag
    def payment_discipline_flag(self):

        if "on_time_flag" not in self.df.columns:
            return False
        on_time_ratio = (
            self.df["on_time_flag"]
            .astype(bool)
            .mean()
        )
        return bool(on_time_ratio >= 0.8)

    # Utility stability score
    def utility_stability_score(self):

        amounts = pd.to_numeric(
            self.df.get("bill_amount"),
            errors="coerce"
        )

        mean = amounts.mean()
        std = amounts.std()

        if pd.isna(mean) or mean == 0:
            return None

        return round(float(std / mean), 4)

    # JSON cleaner
    def clean_feature_dict(self, feature_dict):

        cleaned = {}

        for key, value in feature_dict.items():
            # Handle NaN
            if pd.isna(value):
                cleaned[key] = None
            # Handle NumPy integers
            elif isinstance(value, np.integer):
                cleaned[key] = int(value)
            # Handle NumPy floats
            elif isinstance(value, np.floating):
                cleaned[key] = float(value)

            else:
                cleaned[key] = value

        return cleaned

    def build_features(self) -> Dict:
        features = {

            "avg_bill_amount":
                self.avg_bill_amount(),

            "max_bill_amount":
                self.max_bill_amount(),

            "payment_discipline_flag":
                self.payment_discipline_flag(),

            "utility_stability_score":
                self.utility_stability_score()
        }
        return self.clean_feature_dict(features)