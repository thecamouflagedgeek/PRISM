
import pandas as pd
import numpy as np
from typing import Dict, Any


class UtilityFeatureEngineer:
    """
    Production-grade utility feature engineering module.

    Purpose:
    Converts raw utility/bill payment data into structured risk signals
    aligned with credit scorecard modeling (Siddiqi-style interpretability).

    Output features:
    - utility_stability (0–1)
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    # ─────────────────────────────────────────────
    # MAIN ENTRY POINT
    # ─────────────────────────────────────────────
    def build_features(self) -> Dict[str, Any]:

        return {
            "payment_discipline_flag": self._payment_discipline_flag(),
            "utility_stability": self._utility_stability(),
        }

    # ─────────────────────────────────────────────
    # FEATURE 1: PAYMENT DISCIPLINE
    # ─────────────────────────────────────────────
    def _payment_discipline_flag(self) -> float:
        """
        Measures whether user pays utility bills on time.

        Logic:
        - If dataset contains explicit "on_time_payment" → use it
        - Else fallback heuristic based on available columns
        """

        if self.df is None or len(self.df) == 0:
            return 0.0

        # Case 1: explicit flag exists
        if "on_time_payment" in self.df.columns:
            return float(self.df["on_time_payment"].mean())

        # Case 2: derived heuristic
        if "delay_days" in self.df.columns:
            # normalize delay (higher delay = worse)
            return float(np.clip(1 - (self.df["delay_days"].mean() / 30), 0, 1))

        # Case 3: fallback (no data)
        return 0.5  # neutral risk

    # ─────────────────────────────────────────────
    # FEATURE 2: UTILITY STABILITY SCORE
    # ─────────────────────────────────────────────
    def _utility_stability(self) -> float:
        """
        Measures consistency of utility payments.

        Higher = stable payer
        Lower = volatile / risky payer
        """

        if self.df is None or len(self.df) == 0:
            return 0.0

        score_components = []

        # variability in bill amount
        if "bill_amount" in self.df.columns:
            cv = self._coefficient_of_variation(self.df["bill_amount"])
            score_components.append(1 / (1 + cv))  # stable spending = better

        # missing payment frequency
        if "missed_payments" in self.df.columns:
            miss_rate = self.df["missed_payments"].mean()
            score_components.append(1 - miss_rate)

        # consistency over time (if timestamp exists)
        if "payment_date" in self.df.columns:
            score_components.append(self._time_consistency_score())

        if not score_components:
            return 0.5  # neutral default

        return float(np.clip(np.mean(score_components), 0, 1))

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────
    def _coefficient_of_variation(self, series: pd.Series) -> float:
        mean = series.mean()
        std = series.std()
        if mean == 0:
            return 0.0
        return std / mean

    def _time_consistency_score(self) -> float:
        """
        Measures how regularly payments happen over time.
        Higher variance in gaps = worse score.
        """

        try:
            dates = pd.to_datetime(self.df["payment_date"])
            gaps = dates.sort_values().diff().dt.days.dropna()

            if len(gaps) == 0:
                return 0.5

            cv = self._coefficient_of_variation(gaps)
            return 1 / (1 + cv)

        except Exception:
            return 0.5