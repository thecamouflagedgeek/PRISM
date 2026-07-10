import pandas as pd
import numpy as np
import re


class SalaryFeatureEngineer:

    def __init__(self, data: dict):
        self.data = data
    def _safe_value(self, key: str) -> float:
        val = self.data.get(key, 0)
        if val is None:
            return 0.0
        if isinstance(val, str):
            # Strip arithmetic expressions or garbage the LLM might return
            val = val.strip()
            # Remove currency symbols and commas
            val = re.sub(r'[₹$,]', '', val)
            # If it looks like an expression (e.g. "30000+5000"), reject it
            if re.search(r'[+\-*/]', val):
                return 0.0
            try:
                return float(val)
            except ValueError:
                return 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0
    
    def _derive_gross(self):
        """Best-effort gross salary derivation when LLM returns null."""
        gross = self._safe_value("gross_salary") 
        if gross > 0:
            return gross
        net = self._safe_value("net_salary")
        # Fallback 1: net + deductions
        deductions = self._safe_value("deductions")
        if net > 0 and deductions > 0:
            return net + deductions

        # Fallback 2: sum of known components
        basic = self._safe_value("basic_salary")
        hra   = self._safe_value("hra")
        other = self._safe_value("other_allowances")
        components = basic + hra + other
        if components > 0:
            return components

        # Fallback 3: can't derive — return 0
        return 0

    def net_to_gross_ratio(self):
        gross = self._derive_gross()
        net   = self._safe_value("net_salary")
        if gross == 0:
            return 0
        return round(net / gross, 4)
    
    def income_overstate_ratio(self):
        gross = self._derive_gross()
        net   = self._safe_value("net_salary")
        if net <= 0:
            return 0
        return round(gross / net, 4)

    def pf_contribution_flag(self):
        pf     = self._safe_value("pf")
        pf_alt = self._safe_value("pf_deduction")
        return bool(pf > 0 or pf_alt > 0)

    def salary_consistency_score(self):
        return 1 if self._safe_value("net_salary") > 0 else 0

    def build_features(self):
        return {
            "net_to_gross_ratio":       self.net_to_gross_ratio(),
            "pf_contribution_flag":     self.pf_contribution_flag(),
            "income_overstate_ratio":   self.income_overstate_ratio(),
            "salary_consistency_score": self.salary_consistency_score(),
        }