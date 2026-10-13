"""
PRISM - BIN STABILITY & STATISTICAL SIGNIFICANCE AUDIT

Purpose:
    Validate whether adjacent OptimalBinning bins have statistically
    meaningful differences in event rates and WoE.

IMPORTANT:
    - Read-only audit
    - Does NOT modify binning artifacts
    - Does NOT retrain the model
    - Does NOT change thresholds
    - Does NOT merge bins automatically

Run from:
    backend/scoring/

Expected artifacts:
    artifacts/binning.pkl
    artifacts/woe_datasets.pkl
"""

import os
import warnings

import joblib
import numpy as np
import pandas as pd

from scipy.stats import chi2_contingency, fisher_exact


# ============================================================================
# CONFIGURATION
# ============================================================================

ARTIFACT_DIR = "artifacts"

BINNING_FILE = os.path.join(ARTIFACT_DIR, "binning.pkl")
WOE_FILE = os.path.join(ARTIFACT_DIR, "woe_datasets.pkl")

OUTPUT_AUDIT = "bin_stability_audit.csv"
OUTPUT_SUMMARY = "bin_stability_summary.csv"

FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

ALPHA = 0.05

# Minimum total observations in a bin before treating it as reasonably sized.
MIN_BIN_COUNT = 50

# Minimum expected cell count used to decide whether chi-square is suitable.
MIN_EXPECTED_COUNT = 5


# ============================================================================
# LOAD ARTIFACTS
# ============================================================================

def load_artifacts():
    print("Loading historical baseline artifacts...")

    if not os.path.exists(BINNING_FILE):
        raise FileNotFoundError(
            f"Missing binning artifact: {BINNING_FILE}"
        )

    if not os.path.exists(WOE_FILE):
        raise FileNotFoundError(
            f"Missing WoE artifact: {WOE_FILE}"
        )

    binning_models = joblib.load(BINNING_FILE)
    woe_data = joblib.load(WOE_FILE)

    print("Loaded:")
    print(f"  Binning models : {type(binning_models)}")
    print(f"  WoE artifact   : {type(woe_data)}")

    if isinstance(woe_data, dict):
        if "X_train_woe" in woe_data:
            print(f"  Training rows  : {len(woe_data['X_train_woe'])}")
        else:
            print("  Training rows  : unavailable")

    return binning_models, woe_data


# ============================================================================
# BIN TABLE CLEANING
# ============================================================================

def clean_binning_table(table):
    """
    Keep only genuine numerical bins.

    OptimalBinning tables can contain:
        - numerical bins
        - Special
        - Missing
        - Totals

    The latter must not participate in adjacent numerical-bin testing.
    """

    if table is None or table.empty:
        return pd.DataFrame()

    df = table.copy()

    if "Bin" not in df.columns:
        return pd.DataFrame()

    # Convert bin labels to strings for safe filtering.
    df["Bin"] = df["Bin"].astype(str).str.strip()

    # Remove metadata/non-numerical rows.
    excluded = {
        "",
        "Totals",
        "Total",
        "Special",
        "Missing",
        "Missing values",
        "Special values",
    }

    df = df[~df["Bin"].isin(excluded)].copy()

    # WoE must be numeric for the audit.
    if "WoE" in df.columns:
        df["WoE"] = pd.to_numeric(df["WoE"], errors="coerce")

    # Event rate must be numeric.
    if "Event rate" in df.columns:
        df["Event rate"] = pd.to_numeric(
            df["Event rate"],
            errors="coerce"
        )

    # Count/event/non-event must be numeric.
    for col in ["Count", "Event", "Non-event", "IV"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

    # Only retain actual bins with valid WoE and event rate.
    required = ["WoE", "Event rate"]

    for col in required:
        if col not in df.columns:
            return pd.DataFrame()

    df = df.dropna(
        subset=["WoE", "Event rate"]
    ).reset_index(drop=True)

    return df


# ============================================================================
# STATISTICAL TEST
# ============================================================================

def compare_adjacent_bins(bin_a, bin_b):
    """
    Compare two adjacent bins.

    Uses:
        Fisher exact test when counts are small.
        Chi-square test otherwise.

    Contingency table:

                    Event    Non-event
        Bin A         EA         NA
        Bin B         EB         NB
    """

    event_a = int(bin_a["Event"])
    non_event_a = int(bin_a["Non-event"])

    event_b = int(bin_b["Event"])
    non_event_b = int(bin_b["Non-event"])

    contingency = np.array([
        [event_a, non_event_a],
        [event_b, non_event_b],
    ])

    # Invalid table.
    if contingency.sum() == 0:
        return np.nan, "UNTESTABLE"

    # If any row has no observations, comparison is invalid.
    if contingency.sum(axis=1).min() == 0:
        return np.nan, "UNTESTABLE"

    # Expected counts for chi-square decision.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            chi2, p_chi, dof, expected = chi2_contingency(
                contingency,
                correction=False
            )
    except Exception:
        return np.nan, "UNTESTABLE"

    # Use Fisher when expected counts are small.
    if np.any(expected < MIN_EXPECTED_COUNT):
        try:
            _, p_value = fisher_exact(contingency)
            return float(p_value), "FISHER_EXACT"
        except Exception:
            return np.nan, "UNTESTABLE"

    return float(p_chi), "CHI_SQUARE"


# ============================================================================
# SINGLE FEATURE AUDIT
# ============================================================================

def audit_feature(feature, binning_model):
    """
    Audit adjacent numerical bins for one feature.
    """

    print("\n" + "-" * 75)
    print(f"FEATURE: {feature}")
    print("-" * 75)

    try:
        table = binning_model.binning_table.build()
    except Exception as exc:
        print(f"Could not build binning table: {exc}")
        return []

    numeric_bins = clean_binning_table(table)

    print(f"\nNumber of numerical bins: {len(numeric_bins)}")

    if numeric_bins.empty:
        print("No usable numerical bins found.")
        return []

    print("\nBin statistics:")

    display_columns = [
        col
        for col in [
            "Bin",
            "Count",
            "Event",
            "Non-event",
            "Event rate",
            "WoE",
            "IV",
        ]
        if col in numeric_bins.columns
    ]

    print(
        numeric_bins[display_columns].to_string(
            index=False
        )
    )

    results = []

    # ------------------------------------------------------------------------
    # Adjacent-bin comparisons
    # ------------------------------------------------------------------------

    for i in range(len(numeric_bins) - 1):

        current = numeric_bins.iloc[i]
        nxt = numeric_bins.iloc[i + 1]

        current_bin = str(current["Bin"])
        next_bin = str(nxt["Bin"])

        current_count = int(current["Count"])
        next_count = int(nxt["Count"])

        current_event_rate = float(current["Event rate"])
        next_event_rate = float(nxt["Event rate"])

        current_woe = float(current["WoE"])
        next_woe = float(nxt["WoE"])

        event_rate_difference = (
            next_event_rate - current_event_rate
        )

        woe_difference = (
            next_woe - current_woe
        )

        abs_event_rate_difference = abs(
            event_rate_difference
        )

        abs_woe_difference = abs(
            woe_difference
        )

        # ------------------------------------------------------------
        # Statistical test
        # ------------------------------------------------------------

        p_value, test_used = compare_adjacent_bins(
            current,
            nxt
        )

        # ------------------------------------------------------------
        # Bin size status
        # ------------------------------------------------------------

        if (
            current_count < MIN_BIN_COUNT
            or next_count < MIN_BIN_COUNT
        ):
            size_status = "SMALL_BIN"
        else:
            size_status = "OK"

        # ------------------------------------------------------------
        # Statistical status
        # ------------------------------------------------------------

        if np.isnan(p_value):
            significance_status = "UNTESTABLE"

        elif p_value < ALPHA:
            significance_status = "SIGNIFICANT"

        else:
            significance_status = "NOT_SIGNIFICANT"

        # ------------------------------------------------------------
        # Combined interpretation
        # ------------------------------------------------------------

        if significance_status == "UNTESTABLE":
            status = "UNTESTABLE"

        elif significance_status == "SIGNIFICANT":
            if size_status == "SMALL_BIN":
                status = "SIGNIFICANT_SMALL"
            else:
                status = "SIGNIFICANT_MEANINGFUL"

        else:
            if size_status == "SMALL_BIN":
                status = "SMALL_BIN_NOT_SIGNIFICANT"
            else:
                status = "NOT_SIGNIFICANT"

        # ------------------------------------------------------------
        # Monotonic direction
        # ------------------------------------------------------------

        if event_rate_difference > 0:
            event_direction = "INCREASE"

        elif event_rate_difference < 0:
            event_direction = "DECREASE"

        else:
            event_direction = "NO_CHANGE"

        if woe_difference > 0:
            woe_direction = "INCREASE"

        elif woe_difference < 0:
            woe_direction = "DECREASE"

        else:
            woe_direction = "NO_CHANGE"

        result = {
            "feature": feature,
            "bin_1": current_bin,
            "bin_2": next_bin,

            "count_1": current_count,
            "count_2": next_count,

            "event_rate_1": current_event_rate,
            "event_rate_2": next_event_rate,

            "event_rate_difference": event_rate_difference,
            "abs_event_rate_difference": abs_event_rate_difference,

            "woe_1": current_woe,
            "woe_2": next_woe,

            "woe_difference": woe_difference,
            "abs_woe_difference": abs_woe_difference,

            "p_value": p_value,
            "test_used": test_used,

            "size_status": size_status,
            "significance_status": significance_status,
            "event_rate_direction": event_direction,
            "woe_direction": woe_direction,

            "status": status,
        }

        results.append(result)

        # ------------------------------------------------------------
        # Console output
        # ------------------------------------------------------------

        print("\nAdjacent bins:")
        print(f"  {current_bin}")
        print(f"  {next_bin}")

        print(f"  Counts: {current_count} vs {next_count}")

        print(
            f"  Event rate: "
            f"{current_event_rate:.4f} -> "
            f"{next_event_rate:.4f}"
        )

        print(
            f"  Event-rate difference: "
            f"{event_rate_difference:+.4f}"
        )

        print(
            f"  WoE: "
            f"{current_woe:.4f} -> "
            f"{next_woe:.4f}"
        )

        print(
            f"  WoE difference: "
            f"{woe_difference:+.4f}"
        )

        if np.isnan(p_value):
            print("  p-value: unavailable")
        else:
            print(f"  p-value: {p_value:.6f}")

        print(f"  Test: {test_used}")
        print(f"  Status: {status}")

    return results


# ============================================================================
# FEATURE SUMMARY
# ============================================================================

def summarize_feature(feature, feature_results):
    """
    Generate a high-level summary for one feature.
    """

    if not feature_results:
        return {
            "feature": feature,
            "comparisons": 0,
            "significant_meaningful": 0,
            "significant_small": 0,
            "not_significant": 0,
            "small_bin_not_significant": 0,
            "untestable": 0,
            "overall_status": "INSUFFICIENT_DATA",
        }

    df = pd.DataFrame(feature_results)

    significant_meaningful = int(
        (df["status"] == "SIGNIFICANT_MEANINGFUL").sum()
    )

    significant_small = int(
        (df["status"] == "SIGNIFICANT_SMALL").sum()
    )

    not_significant = int(
        (df["status"] == "NOT_SIGNIFICANT").sum()
    )

    small_bin_not_significant = int(
        (df["status"] == "SMALL_BIN_NOT_SIGNIFICANT").sum()
    )

    untestable = int(
        (df["status"] == "UNTESTABLE").sum()
    )

    if significant_meaningful > 0:
        overall_status = "STABLE_DIFFERENCES"

    elif significant_small > 0:
        overall_status = "REVIEW_SMALL_BINS"

    elif small_bin_not_significant > 0:
        overall_status = "REVIEW_SMALL_BINS"

    elif not_significant == len(df):
        overall_status = "NO_STRONG_EVIDENCE"

    elif untestable == len(df):
        overall_status = "INSUFFICIENT_DATA"

    else:
        overall_status = "REVIEW_BIN_BOUNDARIES"

    return {
        "feature": feature,
        "comparisons": len(df),
        "significant_meaningful": significant_meaningful,
        "significant_small": significant_small,
        "not_significant": not_significant,
        "small_bin_not_significant": small_bin_not_significant,
        "untestable": untestable,
        "overall_status": overall_status,
    }


# ============================================================================
# MAIN
# ============================================================================

def main():

    print("=" * 75)
    print("PRISM - BIN STABILITY & STATISTICAL SIGNIFICANCE AUDIT")
    print("=" * 75)

    binning_models, woe_data = load_artifacts()

    all_results = []
    summary_results = []

    print("\n" + "=" * 75)
    print("ADJACENT BIN ANALYSIS")
    print("=" * 75)

    for feature in FEATURES:

        if feature not in binning_models:
            print(f"\nWARNING: No binning model found for {feature}")
            summary_results.append({
                "feature": feature,
                "comparisons": 0,
                "significant_meaningful": 0,
                "significant_small": 0,
                "not_significant": 0,
                "small_bin_not_significant": 0,
                "untestable": 0,
                "overall_status": "INSUFFICIENT_DATA",
            })
            continue

        feature_results = audit_feature(
            feature,
            binning_models[feature]
        )

        all_results.extend(feature_results)

        summary_results.append(
            summarize_feature(
                feature,
                feature_results
            )
        )

    # =========================================================================
    # SAVE DETAILED AUDIT
    # =========================================================================

    if all_results:
        audit_df = pd.DataFrame(all_results)

        audit_df.to_csv(
            OUTPUT_AUDIT,
            index=False
        )

        print("\n" + "=" * 75)
        print("DETAILED AUDIT SAVED")
        print("=" * 75)

        print(f"File: {os.path.abspath(OUTPUT_AUDIT)}")
        print(f"Comparisons: {len(audit_df)}")

    else:
        print("\nNo adjacent-bin comparisons were generated.")

    # =========================================================================
    # SAVE SUMMARY
    # =========================================================================

    summary_df = pd.DataFrame(summary_results)

    summary_df.to_csv(
        OUTPUT_SUMMARY,
        index=False
    )

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================

    print("\n" + "=" * 75)
    print("FEATURE SUMMARY")
    print("=" * 75)

    print(
        summary_df.to_string(
            index=False
        )
    )

    print("\n" + "=" * 75)
    print("INTERPRETATION")
    print("=" * 75)

    for _, row in summary_df.iterrows():

        feature = row["feature"]
        status = row["overall_status"]

        if status == "STABLE_DIFFERENCES":
            print(
                f"\n{feature}:"
                "\n  Statistically meaningful adjacent-bin "
                "differences detected."
                "\n  Keep current bins for now; no automatic merging."
            )

        elif status == "REVIEW_SMALL_BINS":
            print(
                f"\n{feature}:"
                "\n  Small-bin or small-sample issue detected."
                "\n  Review boundaries before considering any merge."
            )

        elif status == "NO_STRONG_EVIDENCE":
            print(
                f"\n{feature}:"
                "\n  No strong statistical evidence that adjacent "
                "bins differ."
                "\n  Candidate for boundary review, not automatic merging."
            )

        elif status == "REVIEW_BIN_BOUNDARIES":
            print(
                f"\n{feature}:"
                "\n  Mixed evidence across adjacent bins."
                "\n  Review individual boundaries."
            )

        else:
            print(
                f"\n{feature}:"
                "\n  Insufficient evidence for a stability conclusion."
            )

    print("\n" + "=" * 75)
    print("AUDIT COMPLETE")
    print("=" * 75)

    print(
        "\nIMPORTANT:"
        "\n  No artifacts were modified."
        "\n  No model was retrained."
        "\n  No thresholds were changed."
        "\n  No bins were automatically merged."
    )


if __name__ == "__main__":
    main()