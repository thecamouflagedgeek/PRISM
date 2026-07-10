import pandas as pd
import numpy as np
from typing import Dict

# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD LISTS
# ─────────────────────────────────────────────────────────────────────────────

EMI_KEYWORDS = [
    "emi", "loan", "finance", "home credit", "bajaj", "hdfc ergo",
    "axis finance", "emi payment", "ecs", "nach",
]

SALARY_KEYWORDS = [
    "salary", "sal", "payroll", "wages", "salary credit", "salary transfer",
]

# Minimum transactions required before we trust any derived feature.
# Mirrors the gate in BankParser, but enforced again here so this class
# never silently computes features on obviously-incomplete data, even if
# it's ever called from a path that skips the parser-level check.
MIN_TRANSACTIONS_REQUIRED = 2


class BankFeatureEngineerError(Exception):
    """Raised when the input DataFrame is too sparse or too noisy to trust."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# BANK FEATURE ENGINEER
# ─────────────────────────────────────────────────────────────────────────────

class BankFeatureEngineer:
    """
    Converts a validated bank statement DataFrame into credit-risk features
    aligned with the PRISM WoE logistic scorecard.

    Features produced
    -----------------
    mean_monthly_credit   : Average monthly inflow (INR). Measures income scale.
    cashflow_cv           : Coefficient of variation of monthly total flow.
                            Low CV = stable income; high CV = erratic/lumpy inflows.
    min_balance_l3m       : Minimum closing balance in the last 3 months, computed
                            AFTER outlier-filtering closing_balance (see
                            _clean_closing_balance). Proxy for liquidity buffer.
    credit_debit_ratio    : total_credit / implied_total_debit.
                            > 1 means net saver; < 1 means net spender.
                            When the parser fails to tag any DR rows (all rows
                            appear as CR), we reconstruct implied debit using the
                            balance-delta method so the ratio is never zero by
                            default.
    salary_regularity_flag: True if salary-like credits appear in ≥ 3 distinct months.
    emi_detection_flag    : True if any EMI / loan-repayment narration is present.
    income_overstate_ratio: total_credits / salary_credits. Measures how much of
                            the credit flow is NOT explainable by salary; a proxy
                            for informal / undisclosed income.

    Balance-delta fallback for credit_debit_ratio
    ---------------------------------------------
    When total_debit == 0 (parser could not classify any row as DR):

        implied_debit = total_credit − (balance_last − balance_first)

    Derivation:
        By the fundamental accounting identity:
            balance_t = balance_{t-1} + credit_t − debit_t
        Summing over all rows:
            balance_last − balance_first = Σ credit − Σ debit
        Therefore:
            Σ debit = Σ credit − (balance_last − balance_first)

    This is exact when closing_balance is reliable (standard bank statement layout).
    If implied_debit ≤ 0 after the calculation (e.g. balance_last >> balance_first,
    meaning the account grew purely on credits with no outflows visible), we fall back
    to implied_debit = total_credit * 0.5, which encodes a conservative 2:1 ratio
    rather than infinity.

    Outlier handling for closing_balance
    -------------------------------------
    OCR/parsing errors frequently corrupt individual closing_balance values —
    e.g. picking up a reference number fragment instead of the real balance.
    A single garbage near-zero balance can wreck min_balance_l3m and, in turn,
    the score, even when the rest of the extraction is fine. Before computing
    min_balance_l3m, we drop closing_balance values that are implausible
    relative to the statement's overall balance distribution (see
    _clean_closing_balance for the exact rule).
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

        if self.df.empty:
            raise BankFeatureEngineerError(
                "Validated bank DataFrame is empty — cannot engineer features."
            )

        if len(self.df) < MIN_TRANSACTIONS_REQUIRED:
            raise BankFeatureEngineerError(
                f"Only {len(self.df)} transaction rows reached feature engineering; "
                f"minimum required is {MIN_TRANSACTIONS_REQUIRED}. Refusing to compute "
                f"features on data this sparse — extraction likely failed upstream."
            )

        self._prepare()

    # ─────────────────────────────────────────────
    # PREPARATION
    # ─────────────────────────────────────────────

    def _prepare(self):
        self.df.columns = [c.lower() for c in self.df.columns]

        self.df["date"] = pd.to_datetime(self.df["date"], errors="coerce", dayfirst=True, format="mixed")
        self.df["amount"] = pd.to_numeric(self.df["amount"], errors="coerce")
        self.df["closing_balance"] = pd.to_numeric(self.df["closing_balance"], errors="coerce")

        self.df["type"] = (
            self.df["type"]
            .astype(str)
            .str.upper()
            .str.strip()
        )
        self.df["narration"] = (
            self.df["narration"]
            .astype(str)
            .fillna("")
            .str.lower()
        )
        self.df["month"] = self.df["date"].dt.to_period("M")

        # Pre-compute slices used by multiple methods
        self._cr_rows = self.df[self.df["type"] == "CR"]
        self._dr_rows = self.df[self.df["type"] == "DR"]

        # Cleaned balance series used specifically for min_balance_l3m
        self._clean_balance_df = self._clean_closing_balance(self.df)

    # ─────────────────────────────────────────────
    # OUTLIER-FILTERED CLOSING BALANCE
    # ─────────────────────────────────────────────

    def _clean_closing_balance(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Flags and drops closing_balance values that are implausible given the
        rest of the statement's balance distribution — the pattern seen when
        OCR/parsing grabs a stray digit or reference-number fragment instead
        of the true balance column.

        Rule: using the median absolute deviation (MAD) of closing_balance,
        drop any row whose balance is more than 10x the median distance from
        the median. This catches single-row collapses to near-zero (e.g.
        0.05, 0.30 next to values in the thousands) without needing a hardcoded
        threshold that would break on genuinely low-balance accounts.
        """
        balances = df["closing_balance"].dropna()

        if len(balances) < 5:
            # Not enough data to detect outliers meaningfully; trust as-is
            return df

        median = balances.median()
        mad = (balances - median).abs().median()

        if mad == 0:
            # All balances identical or near-identical; nothing to filter
            return df

        # Modified z-score using MAD (robust to skew, unlike std-based z-score)
        modified_z = 0.6745 * (df["closing_balance"] - median).abs() / mad

        outlier_mask = modified_z > 10  # conservative threshold
        n_outliers = int(outlier_mask.sum())

        if n_outliers > 0:
            print(
                f"[BankFeatureEngineer] Dropping {n_outliers} closing_balance outlier(s) "
                f"as likely OCR/parsing artifacts: "
                f"{df.loc[outlier_mask, 'closing_balance'].tolist()}"
            )

        cleaned = df.copy()
        cleaned.loc[outlier_mask, "closing_balance"] = np.nan
        return cleaned

    # ─────────────────────────────────────────────
    # FEATURE 1 — MEAN MONTHLY CREDIT
    # ─────────────────────────────────────────────

    def mean_monthly_credit(self) -> float:
        """Average monthly CR inflow in INR."""
        monthly = self._cr_rows.groupby("month")["amount"].sum()
        if monthly.empty:
            return 0.0
        return round(float(monthly.mean()), 2)

    # ─────────────────────────────────────────────
    # FEATURE 2 — CASHFLOW COEFFICIENT OF VARIATION
    # ─────────────────────────────────────────────

    def cashflow_cv(self) -> float:
        """
        CV of monthly total transaction amount.
        Uses all rows (CR + DR) so that months with high outflows pull the
        variance up — a genuine signal of cash-flow instability.
        """
        monthly = self.df.groupby("month")["amount"].sum()
        if len(monthly) < 2:
            return 0.0
        mean = monthly.mean()
        if mean == 0:
            return 0.0
        return round(float(monthly.std() / mean), 4)

    # ─────────────────────────────────────────────
    # FEATURE 3 — MINIMUM BALANCE (LAST 3 MONTHS)
    # ─────────────────────────────────────────────

    def min_balance_l3m(self) -> float:
        """
        Minimum closing balance over the last 3 calendar months, computed on
        the outlier-filtered balance series (see _clean_closing_balance).
        """
        df = self._clean_balance_df
        latest = df["date"].max()
        last_3m = df[df["date"] >= latest - pd.DateOffset(months=3)]

        valid_balances = last_3m["closing_balance"].dropna()
        if valid_balances.empty:
            print(
                "[BankFeatureEngineer] No valid closing_balance values in last 3 months "
                "after outlier filtering — returning 0.0 (treated as missing downstream)."
            )
            return 0.0

        return round(float(valid_balances.min()), 2)

    # ─────────────────────────────────────────────
    # FEATURE 4 — CREDIT / DEBIT RATIO
    # ─────────────────────────────────────────────

    def credit_debit_ratio(self) -> float:
        """
        total_credit / total_debit.

        When the statement parser could not classify any transactions as DR
        (all rows tagged CR — common in single-column PDF layouts), we derive
        implied_debit from the balance delta:

            implied_debit = total_credit − (balance_last − balance_first)

        See class docstring for the accounting-identity derivation.
        """
        total_credit = float(self._cr_rows["amount"].sum())
        total_debit  = float(self._dr_rows["amount"].sum())

        print(f"[BankFeatureEngineer] CR={total_credit:.2f}  DR={total_debit:.2f}")

        if total_debit > 0:
            return round(total_credit / total_debit, 4)

        # ── Balance-delta fallback ────────────────────────────────────────────
        sorted_df = self.df.dropna(subset=["closing_balance"]).sort_values("date")
        if len(sorted_df) < 2:
            print("[BankFeatureEngineer] Fallback: insufficient balance rows → ratio=1.0")
            return 1.0

        balance_first = float(sorted_df["closing_balance"].iloc[0])
        balance_last  = float(sorted_df["closing_balance"].iloc[-1])
        delta         = balance_last - balance_first

        implied_debit = total_credit - delta

        print(
            f"[BankFeatureEngineer] Balance-delta fallback: "
            f"first={balance_first:.2f}  last={balance_last:.2f}  "
            f"delta={delta:.2f}  implied_debit={implied_debit:.2f}"
        )

        if implied_debit <= 0:
            print("[BankFeatureEngineer] implied_debit ≤ 0 → conservative ratio=2.0")
            return 2.0

        return round(total_credit / implied_debit, 4)

    # ─────────────────────────────────────────────
    # FEATURE 5 — SALARY REGULARITY FLAG
    # ─────────────────────────────────────────────

    def salary_regularity_flag(self) -> bool:
        """True if salary-tagged credits appear in ≥ 3 distinct calendar months."""
        mask = self._cr_rows["narration"].str.contains(
            "|".join(SALARY_KEYWORDS), na=False
        )
        salary_txns = self._cr_rows[mask]
        if salary_txns.empty:
            return False
        return int(salary_txns["month"].nunique()) >= 3

    # ─────────────────────────────────────────────
    # FEATURE 6 — EMI DETECTION FLAG
    # ─────────────────────────────────────────────

    def emi_detection_flag(self) -> bool:
        """True if any narration matches known EMI / loan-repayment keywords."""
        return bool(
            self.df["narration"].str.contains(
                "|".join(EMI_KEYWORDS), na=False
            ).any()
        )

    # ─────────────────────────────────────────────
    # FEATURE 7 — INCOME OVERSTATE RATIO
    # ─────────────────────────────────────────────

    def income_overstate_ratio(self) -> float:
        """
        total_credits / salary_credits.

        = 1.0  → 100 % of credits are salary-labelled (consistent declared income)
        > 1.0  → unexplained inflows exist (could be business, gifts, informal income)
        = 0.0  → no salary narration found at all (returned when salary_total == 0
                  to avoid division by zero; handled downstream as missing feature)
        """
        salary_mask = self._cr_rows["narration"].str.contains(
            "|".join(SALARY_KEYWORDS), na=False
        )
        salary_total = float(self._cr_rows[salary_mask]["amount"].sum())
        all_credits  = float(self._cr_rows["amount"].sum())

        if salary_total == 0:
            return 0.0
        return round(all_credits / salary_total, 4)

    # ─────────────────────────────────────────────
    # BUILD FEATURES — public entry point
    # ─────────────────────────────────────────────

    def build_features(self) -> Dict:
        return {
            "mean_monthly_credit":    self.mean_monthly_credit(),
            "cashflow_cv":            self.cashflow_cv(),
            "min_balance_l3m":        self.min_balance_l3m(),
            "credit_debit_ratio":     self.credit_debit_ratio(),
            "salary_regularity_flag": self.salary_regularity_flag(),
            "emi_detection_flag":     self.emi_detection_flag(),
            "income_overstate_ratio": self.income_overstate_ratio(),
        }