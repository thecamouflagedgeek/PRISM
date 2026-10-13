import pandas as pd
import numpy as np


class SalaryFeatureEngineer:

    def __init__(self, data:dict):
        self.data=data

    def _safe_value(self, key):
        value = self.data.get(key)
        if value is None:
            return None
        try:
            value = float(value)
            return value if np.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    def net_to_gross_ratio(self):

        gross = self._safe_value("gross_salary")
        net = self._safe_value("net_salary")

        if gross is None or net is None or gross <= 0:
            return None
        return net / gross

    def pf_contribution_flag(self):

        pf = self._safe_value("pf")
        pf_alt = self._safe_value("pf_deduction")
        if pf is None and pf_alt is None:
            return None
        return bool((pf is not None and pf > 0) or (pf_alt is not None and pf_alt > 0))

    def income_overstate_ratio(self):

        gross = self._safe_value("gross_salary")
        net = self._safe_value("net_salary")

        if gross is None or net is None or net <= 0:
            return None

        return round(gross / net, 4)

    def salary_consistency_score(self):

        net = self._safe_value("net_salary")

        if net is not None and net > 0:
            return 1
        return None

    def build_features(self):

        features = {
            "net_to_gross_ratio": self.net_to_gross_ratio(),
            "pf_contribution_flag": self.pf_contribution_flag(),
            "income_overstate_ratio": self.income_overstate_ratio(),
            "salary_consistency_score": self.salary_consistency_score(),
        }

        return features
