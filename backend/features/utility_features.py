import pandas as pd
import numpy as np
from typing import Dict, Any


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FEATURE ENGINEER
# ─────────────────────────────────────────────────────────────────────────────

class UtilityFeatureEngineer:
    """
    Converts raw utility bill data into credit-risk features aligned with
    the PRISM WoE logistic scorecard.

    Input
    -----
    Accepts either:
      - dict   : single bill extracted by UtilityParser / UtilityExtractor
      - DataFrame: multiple bills (multi-month history)

    Features produced
    -----------------
    utility_stability (float, 0–1)
        Composite signal measuring both payment behaviour and bill consistency.
        Mapped directly into the scorecard's `utility_stability` WoE bin.

        Higher = more stable = lower credit risk.

    Mathematical definition
    -----------------------
    We distinguish two data regimes:

    REGIME A — Multi-bill history (≥ 2 rows with amount & payment data)
    ───────────────────────────────────────────────────────────────────
        Component 1: Payment discipline (weight 0.50)
            If explicit on_time_payment column:
                discipline = mean(on_time_payment)        [0, 1]
            Elif delay_days column:
                discipline = clip(1 − mean(delay_days)/30, 0, 1)
            Elif payment_discipline_flag bool/float column:
                discipline = mean(payment_discipline_flag) [0, 1]
            Else:
                discipline = 0.5  (neutral — no payment timing data)

        Component 2: Bill amount stability (weight 0.30)
            CV = std(bill_amount) / mean(bill_amount)     [0, ∞)
            amount_stability = 1 / (1 + CV)               [0, 1]
            Intuition: CV=0 → perfectly stable bills → score 1.0
                       CV=1 → std = mean → score 0.5
                       CV→∞ → wildly varying bills → score → 0

        Component 3: Payment timing consistency (weight 0.20)
            Uses payment_date if available. Measures CV of inter-payment gaps.
            timing_score = 1 / (1 + CV_gaps)
            Omitted when payment_date is absent (weight redistributed).

        utility_stability = weighted_average(components, weights)

    REGIME B — Single bill (most common case: one PDF uploaded)
    ──────────────────────────────────────────────────────────
        With only one bill we have no history to measure, so we use
        available point-in-time signals:

        Component 1: Payment discipline flag (weight 0.60)
            Derived from payment_discipline_flag (bool or float).
            True / 1.0 → 1.0   (bill shows "PAID" / receipt marker)
            0.5         → 0.5   (ambiguous — no paid/unpaid marker found)
            False / 0.0 → 0.2   (not 0.0, because absence of proof ≠ proof of default)

        Component 2: Bill amount reasonableness (weight 0.40)
            A utility bill amount that is very high relative to typical Indian
            residential bills (₹500–₹5000/month) may indicate commercial use
            or an arrear-heavy outstanding — a mild negative signal.

            amount_score = clip(1 − (bill_amount − 5000) / 45000, 0.2, 1.0)

            Calibration:
              ₹500–₹5000  → score 1.0  (normal residential range)
              ₹50,000     → score 0.2  (high commercial / arrear outlier)
              Missing/0   → score 0.6  (neutral — no amount extracted)

        utility_stability = 0.60 * discipline + 0.40 * amount_score

    Regime selection
    ----------------
    REGIME A is used when:  len(df) ≥ 2  AND  bill_amount column is present
    REGIME B is used otherwise (single bill or no bill_amount history).

    Note on payment_discipline_flag
    --------------------------------
    The UtilityExtractor sets this to bool True/False.
    UtilityParser (old path) may set it to 0.5 (neutral float).
    Both are handled. We never propagate 0.5 as a final feature value —
    it is always resolved to a proper [0,1] float in _discipline_score().
    """

    def __init__(self, df):
        if isinstance(df, dict):
            self.df = pd.DataFrame([df])
        elif isinstance(df, pd.DataFrame):
            self.df = df.copy()
        else:
            self.df = pd.DataFrame()

    # ─────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ─────────────────────────────────────────────

    def build_features(self) -> Dict[str, Any]:
        """
        Returns exactly the features expected by scoring_engine._map_features().

        Note: payment_discipline_flag is NOT returned here — it is an internal
        intermediate used to compute utility_stability, not a scorecard feature.
        """
        return {
            "utility_stability": self._utility_stability(),
        }

    # ─────────────────────────────────────────────
    # MAIN FEATURE COMPUTATION
    # ─────────────────────────────────────────────

    def _utility_stability(self) -> float:
        """See class docstring for mathematical definition."""
        try:
            if self.df is None or self.df.empty:
                return 0.5   # no data at all — neutral

            has_amounts  = (
                "bill_amount" in self.df.columns
                and self.df["bill_amount"].notna().sum() >= 2
            )
            multi_bill   = len(self.df) >= 2 and has_amounts

            if multi_bill:
                return self._regime_a()
            else:
                return self._regime_b()

        except Exception as e:
            print(f"[UtilityFeatureEngineer] _utility_stability error: {e}")
            return 0.5   # never propagate NaN to scorer

    # ─────────────────────────────────────────────
    # REGIME A — multi-bill history
    # ─────────────────────────────────────────────

    def _regime_a(self) -> float:
        components = []
        weights    = []

        # Component 1: payment discipline (w=0.50)
        discipline = self._discipline_score()
        components.append(discipline)
        weights.append(0.50)

        # Component 2: bill amount stability (w=0.30)
        amounts = self.df["bill_amount"].dropna()
        cv = self._cv(amounts)
        amount_stability = 1.0 / (1.0 + cv)
        components.append(amount_stability)
        weights.append(0.30)

        # Component 3: payment timing consistency (w=0.20, optional)
        if "payment_date" in self.df.columns and self.df["payment_date"].notna().sum() >= 2:
            timing = self._timing_score()
            components.append(timing)
            weights.append(0.20)
        # If timing absent, remaining weight (0.20) flows to discipline & amount
        # proportionally via re-normalization below.

        total_weight = sum(weights)
        score = sum(c * w for c, w in zip(components, weights)) / total_weight

        return float(np.clip(round(score, 4), 0.0, 1.0))

    # ─────────────────────────────────────────────
    # REGIME B — single bill (most common)
    # ─────────────────────────────────────────────

    def _regime_b(self) -> float:
        # Component 1: payment discipline (w=0.60)
        discipline = self._discipline_score()

        # Component 2: bill amount reasonableness (w=0.40)
        amount_score = self._single_bill_amount_score()

        score = 0.60 * discipline + 0.40 * amount_score

        print(
            f"[UtilityFeatureEngineer] Regime B: "
            f"discipline={discipline:.3f}  amount_score={amount_score:.3f}  "
            f"utility_stability={score:.4f}"
        )

        return float(np.clip(round(score, 4), 0.0, 1.0))

    # ─────────────────────────────────────────────
    # DISCIPLINE SCORE (shared by both regimes)
    # ─────────────────────────────────────────────

    def _discipline_score(self) -> float:
        """
        Resolves payment discipline to a float in [0, 1] from whatever
        column is available, in priority order.
        """
        # Priority 1: explicit on_time_payment column
        if "on_time_payment" in self.df.columns:
            val = self.df["on_time_payment"].dropna()
            if len(val) > 0:
                return float(np.clip(val.mean(), 0.0, 1.0))

        # Priority 2: delay_days column
        if "delay_days" in self.df.columns:
            val = self.df["delay_days"].dropna()
            if len(val) > 0:
                return float(np.clip(1.0 - val.mean() / 30.0, 0.0, 1.0))

        # Priority 3: payment_discipline_flag (bool or float)
        if "payment_discipline_flag" in self.df.columns:
            raw = self.df["payment_discipline_flag"].iloc[0]

            if isinstance(raw, bool):
                return 1.0 if raw else 0.2

            if isinstance(raw, (int, float)) and not np.isnan(raw):
                if raw == 1.0 or raw is True:
                    return 1.0
                elif raw == 0.5:
                    # Ambiguous — UtilityParser/UtilityExtractor found no
                    # payment marker. Treat as mild positive (not defaulted,
                    # just no receipt in document).
                    return 0.5
                elif raw == 0.0 or raw is False:
                    return 0.2   # no evidence of payment
                else:
                    # Any other float in [0,1] from a multi-bill aggregation
                    return float(np.clip(raw, 0.0, 1.0))

        # No column found — neutral
        return 0.5

    # ─────────────────────────────────────────────
    # SINGLE BILL AMOUNT REASONABLENESS
    # ─────────────────────────────────────────────

    def _single_bill_amount_score(self) -> float:
        """
        Scores how reasonable the bill amount is for a residential utility bill.

        Score curve:
          ≤ ₹5,000  → 1.0   (normal Indian residential range)
          ₹50,000   → 0.2   (outlier: commercial or heavy arrears)
          Missing   → 0.6   (neutral)
        """
        if "bill_amount" not in self.df.columns:
            return 0.6

        val = self.df["bill_amount"].dropna()
        if len(val) == 0:
            return 0.6

        amount = float(val.iloc[0])
        if amount <= 0:
            return 0.6

        # Linear decay from 5000 to 50000 → score from 1.0 to 0.2
        score = 1.0 - (amount - 5000.0) / 45000.0
        return float(np.clip(round(score, 4), 0.2, 1.0))

    # ─────────────────────────────────────────────
    # TIMING CONSISTENCY (Regime A only)
    # ─────────────────────────────────────────────

    def _timing_score(self) -> float:
        """
        CV of inter-payment gaps in days.
        Low CV = regular payer; high CV = erratic.
        """
        try:
            dates = pd.to_datetime(self.df["payment_date"], errors="coerce").dropna()
            gaps  = dates.sort_values().diff().dt.days.dropna()
            if len(gaps) == 0:
                return 0.5
            cv = self._cv(gaps)
            return float(np.clip(1.0 / (1.0 + cv), 0.0, 1.0))
        except Exception:
            return 0.5

    # ─────────────────────────────────────────────
    # HELPER
    # ─────────────────────────────────────────────

    @staticmethod
    def _cv(series) -> float:
        """Coefficient of variation; returns 0 if mean is zero."""
        s = pd.Series(series).dropna()
        if len(s) == 0:
            return 0.0
        mean = s.mean()
        if mean == 0:
            return 0.0
        return float(s.std() / mean)