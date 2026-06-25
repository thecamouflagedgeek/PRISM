import pandas as pd
import numpy as np


class SalaryFeatureEngineer:

    def __init__(self, data:dict):
        self.data=data

    def _safe_value(self, key):
        value = self.data.get(key)
        
        if value is None:
            return 0
        try:
            return float(value)
        except:
            return 0

    def net_to_gross_ratio(self):

        gross = self._safe_value("gross_salary")
        net = self._safe_value("net_salary")

        if gross == 0:
            return 0
        return net / gross

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