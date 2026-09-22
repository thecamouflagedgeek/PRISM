"""
PRISM - Feature & WoE Baseline Validation

Purpose:
    Read-only audit of the historical PRISM scorecard features.

Checks:
    1. Information Value (IV)
    2. Bin population
    3. Event/default rate per bin
    4. WoE per bin
    5. WoE monotonicity
    6. Suspicious/small bins
    7. Overall feature assessment

IMPORTANT:
    This script does NOT modify, retrain, or regenerate any artifacts.
"""

import os
import warnings
import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_DIR = os.path.join(BASE_DIR, "artifacts")

BINNING_PATH = os.path.join(ARTIFACT_DIR, "binning.pkl")
WOE_PATH = os.path.join(ARTIFACT_DIR, "woe_datasets.pkl")

FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

# A bin below this percentage of observations is flagged.
SMALL_BIN_THRESHOLD = 0.05


# ============================================================
# HELPERS
# ============================================================

def print_header(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def get_bin_table(binner):
    """
    Return the OptBinning table.

    We deliberately keep the Special, Missing and Totals rows
    because they are useful for auditing. They are handled
    separately when calculating monotonicity.
    """
    table = binner.binning_table.build()

    # Reset index in case the returned object has a custom index.
    table = table.reset_index(drop=True)

    return table


def identify_total_row(table):
    """
    Locate the Totals row.
    """
    if "Bin" not in table.columns:
        return None

    matches = table["Bin"].astype(str).str.lower().eq("totals")

    if matches.any():
        return table.index[matches][0]

    return None


def is_special_or_missing(bin_name):
    """
    Identify bins that should not be used when checking
    ordinary numerical monotonicity.
    """
    text = str(bin_name).strip().lower()

    return (
        "missing" in text
        or "special" in text
        or text in {"", "nan", "none"}
    )


def get_ordinary_bins(table):
    """
    Return only normal numerical bins.

    Special/Missing/Totals rows are excluded from monotonicity
    analysis because they are not ordered numerical intervals.
    """
    if "Bin" not in table.columns:
        return table.iloc[0:0]

    mask = ~table["Bin"].apply(is_special_or_missing)

    mask &= ~table["Bin"].astype(str).str.lower().eq("totals")

    return table.loc[mask].copy()


def monotonicity_status(values):
    """
    Determine whether values are monotonically increasing,
    monotonically decreasing, or non-monotonic.

    Equal adjacent values are allowed.
    """
    values = pd.Series(values).dropna().astype(float).values

    if len(values) <= 2:
        return "INSUFFICIENT BINS"

    diffs = np.diff(values)

    increasing = np.all(diffs >= -1e-12)
    decreasing = np.all(diffs <= 1e-12)

    if increasing and decreasing:
        return "CONSTANT"

    if increasing:
        return "MONOTONIC INCREASING"

    if decreasing:
        return "MONOTONIC DECREASING"

    return "NON-MONOTONIC"


def calculate_iv(table):
    """
    Calculate Information Value from ordinary bins only.

    The OptBinning table contains a Totals row whose IV is already
    the sum of the individual bin IVs. Therefore, we must NOT add
    the Totals row to the individual bin IVs.
    """

    if "IV" not in table.columns:
        return np.nan

    # Exclude Totals, Special and Missing rows.
    mask = pd.Series(True, index=table.index)

    if "Bin" in table.columns:
        bin_text = table["Bin"].astype(str).str.strip().str.lower()

        mask &= ~bin_text.eq("totals")
        mask &= ~bin_text.eq("special")
        mask &= ~bin_text.eq("missing")
        mask &= bin_text.ne("")

    iv_values = pd.to_numeric(
        table.loc[mask, "IV"],
        errors="coerce"
    )

    return float(iv_values.sum())

def calculate_bin_percentage(table):
    """
    Calculate bin population percentage.

    OptBinning normally exposes 'Count (%)'.
    """
    if "Count (%)" in table.columns:
        values = pd.to_numeric(table["Count (%)"], errors="coerce")

        return values * 100.0

    if "Count" in table.columns:
        counts = pd.to_numeric(table["Count"], errors="coerce")

        total_row = identify_total_row(table)

        if total_row is not None:
            total = safe_float(table.loc[total_row, "Count"])
        else:
            total = counts.sum()

        if total and not np.isnan(total):
            return counts / total * 100.0

    return pd.Series(np.nan, index=table.index)


def classify_iv(iv):
    """
    Practical IV interpretation for audit purposes.

    These are heuristic ranges, not regulatory thresholds.
    """
    if np.isnan(iv):
        return "UNKNOWN"

    if iv < 0.02:
        return "VERY WEAK"

    if iv < 0.10:
        return "WEAK"

    if iv < 0.30:
        return "MODERATE"

    if iv < 0.50:
        return "STRONG"

    return "VERY STRONG"


# ============================================================
# FEATURE AUDIT
# ============================================================

def audit_feature(feature, binner):
    """
    Audit one OptimalBinning model.
    """

    print_header(f"FEATURE: {feature}")

    table = get_bin_table(binner)

    if table.empty:
        print("ERROR: Empty binning table.")
        return None

    iv = calculate_iv(table)
    iv_class = classify_iv(iv)

    print(f"Information Value : {iv:.6f}")
    print(f"IV Assessment     : {iv_class}")

    print()
    print("Bin-level analysis:")
    print("-" * 100)

    population_pct = calculate_bin_percentage(table)

    display_columns = []

    for col in [
        "Bin",
        "Count",
        "Count (%)",
        "Non-event",
        "Event",
        "Event rate",
        "WoE",
        "IV",
    ]:
        if col in table.columns:
            display_columns.append(col)

    display = table[display_columns].copy()

    # Add population percentage if Count (%) isn't available.
    if "Count (%)" not in display.columns:
        display.insert(
            min(2, len(display.columns)),
            "Population %",
            population_pct.values
        )
    else:
        display["Count (%)"] = pd.to_numeric(
            display["Count (%)"],
            errors="coerce"
        ) * 100.0

    # Make numeric columns readable.
    for col in display.columns:
        if col not in {"Bin"}:
            display[col] = pd.to_numeric(
                display[col],
                errors="coerce"
            )

    print(display.to_string(index=False))

    # --------------------------------------------------------
    # MONOTONICITY
    # --------------------------------------------------------

    ordinary = get_ordinary_bins(table)

    print()
    print("WoE monotonicity:")
    print("-" * 100)

    if "WoE" not in ordinary.columns:
        monotonicity = "WOE COLUMN NOT FOUND"
    else:
        monotonicity = monotonicity_status(ordinary["WoE"])

    print(f"Status: {monotonicity}")

    # Event-rate monotonicity is also useful because WoE can
    # behave differently depending on the event definition.
    if "Event rate" in ordinary.columns:
        event_rate_status = monotonicity_status(
            pd.to_numeric(
                ordinary["Event rate"],
                errors="coerce"
            )
        )

        print(f"Event-rate status: {event_rate_status}")
    else:
        event_rate_status = "EVENT RATE COLUMN NOT FOUND"

    # --------------------------------------------------------
    # SMALL BIN CHECK
    # --------------------------------------------------------

    print()
    print("Small-bin check:")
    print("-" * 100)

    small_bins = []

    for idx, row in ordinary.iterrows():

        if "Count (%)" in table.columns:
            pct = safe_float(row["Count (%)"]) * 100.0
        elif "Count" in table.columns:
            count = safe_float(row["Count"])

            total_row = identify_total_row(table)

            if total_row is not None:
                total_count = safe_float(
                    table.loc[total_row, "Count"]
                )
            else:
                total_count = pd.to_numeric(
                    table["Count"],
                    errors="coerce"
                ).sum()

            pct = (
                count / total_count * 100.0
                if total_count
                else np.nan
            )
        else:
            pct = np.nan

        if not np.isnan(pct) and pct < SMALL_BIN_THRESHOLD * 100:
            small_bins.append(
                (str(row["Bin"]), pct)
            )

    if small_bins:
        print(
            f"WARNING: {len(small_bins)} ordinary bin(s) "
            f"contain less than {SMALL_BIN_THRESHOLD * 100:.1f}% "
            "of observations."
        )

        for bin_name, pct in small_bins:
            print(f"  {bin_name}: {pct:.3f}%")
    else:
        print(
            f"No ordinary bins below "
            f"{SMALL_BIN_THRESHOLD * 100:.1f}%."
        )

    # --------------------------------------------------------
    # BIN COUNT
    # --------------------------------------------------------

    ordinary_bin_count = len(ordinary)

    print()
    print(f"Ordinary numerical bins: {ordinary_bin_count}")

    # --------------------------------------------------------
    # FINAL FEATURE ASSESSMENT
    # --------------------------------------------------------

    issues = []

    if iv < 0.02:
        issues.append("very low IV")

    if monotonicity == "NON-MONOTONIC":
        issues.append("non-monotonic WoE")

    if event_rate_status == "NON-MONOTONIC":
        issues.append("non-monotonic event rate")

    if small_bins:
        issues.append("small bins")

    print()
    print("Feature audit assessment:")
    print("-" * 100)

    if not issues:
        print("PASS - No major structural issue detected.")
    else:
        print("REVIEW REQUIRED")
        for issue in issues:
            print(f"  - {issue}")

    return {
        "feature": feature,
        "iv": iv,
        "iv_assessment": iv_class,
        "woe_monotonicity": monotonicity,
        "event_rate_monotonicity": event_rate_status,
        "ordinary_bins": ordinary_bin_count,
        "small_bin_count": len(small_bins),
        "issues": issues,
    }


# ============================================================
# SUMMARY
# ============================================================

def print_summary(results):
    print_header("FEATURE VALIDATION SUMMARY")

    summary_rows = []

    for result in results:
        summary_rows.append({
            "feature": result["feature"],
            "IV": result["iv"],
            "IV assessment": result["iv_assessment"],
            "WoE monotonicity": result["woe_monotonicity"],
            "Event-rate monotonicity": result[
                "event_rate_monotonicity"
            ],
            "bins": result["ordinary_bins"],
            "small bins": result["small_bin_count"],
            "issues": (
                ", ".join(result["issues"])
                if result["issues"]
                else "None"
            ),
        })

    summary = pd.DataFrame(summary_rows)

    print(
        summary.to_string(
            index=False,
            formatters={
                "IV": lambda x: f"{x:.6f}"
            }
        )
    )

    print()
    print("Interpretation:")
    print("-" * 78)
    print("IV measures the feature's predictive information.")
    print("WoE monotonicity checks whether the fitted risk relationship")
    print("moves consistently across ordered numerical bins.")
    print("Non-monotonic behaviour is not automatically wrong, but")
    print("it should be investigated before changing the binning.")
    print("Small-bin warnings indicate potentially unstable bins.")
    print()
    print("These are diagnostic findings, not model changes.")


# ============================================================
# MAIN
# ============================================================

def main():

    print_header("PRISM - FEATURE & WOE BASELINE VALIDATION")

    # --------------------------------------------------------
    # LOAD ARTIFACTS
    # --------------------------------------------------------

    print()
    print("[1] Loading historical artifacts...")

    if not os.path.exists(BINNING_PATH):
        raise FileNotFoundError(
            f"Binning artifact not found:\n{BINNING_PATH}"
        )

    if not os.path.exists(WOE_PATH):
        raise FileNotFoundError(
            f"WOE artifact not found:\n{WOE_PATH}"
        )

    binning_models = joblib.load(BINNING_PATH)
    woe_data = joblib.load(WOE_PATH)

    print(f"    Binning artifact : {BINNING_PATH}")
    print(f"    WOE artifact     : {WOE_PATH}")

    # --------------------------------------------------------
    # BASIC STRUCTURE CHECK
    # --------------------------------------------------------

    print()
    print("[2] Checking artifact structure...")

    if not isinstance(binning_models, dict):
        raise TypeError(
            "binning.pkl is expected to contain a dictionary."
        )

    print(
        f"    Binning models found: "
        f"{list(binning_models.keys())}"
    )

    if isinstance(woe_data, dict):
        print(
            f"    WOE artifact keys: "
            f"{list(woe_data.keys())}"
        )

    # --------------------------------------------------------
    # AUDIT FEATURES
    # --------------------------------------------------------

    print()
    print("[3] Auditing features...")

    results = []

    for feature in FEATURES:

        if feature not in binning_models:
            print()
            print(
                f"WARNING: No binning model found for "
                f"{feature}. Skipping."
            )
            continue

        result = audit_feature(
            feature,
            binning_models[feature]
        )

        if result is not None:
            results.append(result)

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    if results:
        print_summary(results)

    # --------------------------------------------------------
    # FINAL STATUS
    # --------------------------------------------------------

    print_header("FEATURE VALIDATION COMPLETE")

    print()
    print("No model or artifact was modified.")
    print("No retraining was performed.")
    print("No thresholds were changed.")
    print()


if __name__ == "__main__":
    main()