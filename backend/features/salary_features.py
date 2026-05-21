import pandas as pd
import numpy as np


class SalaryFeatureEngineer:

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def _safe_value(self, column_name):
        """
        Safely extract first value from dataframe column.
        Returns 0 if column missing or empty.
        """

        if column_name not in self.df.columns:
            return 0

        value = pd.to_numeric(
            self.df[column_name],
            errors="coerce"
        ).fillna(0)

        if len(value) == 0:
            return 0

        return float(value.iloc[0])

    def net_to_gross_ratio(self):

        gross = self._safe_value("gross_salary")
        net = self._safe_value("net_salary")

        if gross <= 0:
            return 0

        return round(net / gross, 4)

    def pf_contribution_flag(self):

        pf = self._safe_value("pf")
        pf_alt = self._safe_value("pf_deduction")

        return bool(pf > 0 or pf_alt > 0)

    def income_overstate_ratio(self):

        gross = self._safe_value("gross_salary")
        net = self._safe_value("net_salary")

        if net <= 0:
            return 0

        return round(gross / net, 4)

    def salary_consistency_score(self):

        net = self._safe_value("net_salary")

        if net > 0:
            return 1

        return 0

    def build_features(self):

        features = {
            "net_to_gross_ratio": self.net_to_gross_ratio(),
            "pf_contribution_flag": self.pf_contribution_flag(),
            "income_overstate_ratio": self.income_overstate_ratio(),
            "salary_consistency_score": self.salary_consistency_score(),
        }

        return features