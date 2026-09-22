
"""
PRISM - TRAIN vs TEST BIN STABILITY & PSI AUDIT

Purpose:
    Validate whether the existing OptimalBinning boundaries behave
    consistently between the training and test datasets.

Checks:
    1. Train vs test bin population %
    2. Population Stability Index (PSI)
    3. Train vs test event rate
    4. Event-rate drift
    5. Train vs test WoE
    6. WoE drift
    7. Overall stability classification

IMPORTANT:
    - Read-only audit
    - Does NOT modify binning.pkl
    - Does NOT modify lr_model.pkl
    - Does NOT retrain the model
    - Does NOT change thresholds
    - Does NOT merge bins

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


# ============================================================================
# CONFIGURATION
# ============================================================================

ARTIFACT_DIR = "artifacts"

BINNING_FILE = os.path.join(
    ARTIFACT_DIR,
    "binning.pkl"
)

WOE_FILE = os.path.join(
    ARTIFACT_DIR,
    "woe_datasets.pkl"
)

OUTPUT_BIN_AUDIT = "train_test_bin_stability.csv"
OUTPUT_FEATURE_SUMMARY = "train_test_bin_stability_summary.csv"

FEATURES = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]


# ============================================================================
# STABILITY THRESHOLDS
# ============================================================================

# PSI interpretation:
#
# < 0.10       = little/no population shift
# 0.10 - 0.25  = moderate shift / review
# > 0.25       = substantial shift / unstable
#
# These are screening thresholds, not regulatory limits.

PSI_STABLE = 0.10
PSI_REVIEW = 0.25

# Absolute event-rate difference.
EVENT_RATE_REVIEW = 0.05
EVENT_RATE_UNSTABLE = 0.10

# Absolute WoE difference.
WOE_REVIEW = 0.20
WOE_UNSTABLE = 0.50

# Minimum bin population percentage.
MIN_BIN_PCT = 0.01


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

    binning_models = joblib.load(
        BINNING_FILE
    )

    woe_data = joblib.load(
        WOE_FILE
    )

    print("Loaded:")

    print(
        f"  Binning models : "
        f"{type(binning_models)}"
    )

    print(
        f"  WoE artifact   : "
        f"{type(woe_data)}"
    )

    if "X_train_woe" not in woe_data:
        raise KeyError(
            "woe_datasets.pkl does not contain X_train_woe"
        )

    if "X_test_woe" not in woe_data:
        raise KeyError(
            "woe_datasets.pkl does not contain X_test_woe"
        )

    if "y_train" not in woe_data:
        raise KeyError(
            "woe_datasets.pkl does not contain y_train"
        )

    if "y_test" not in woe_data:
        raise KeyError(
            "woe_datasets.pkl does not contain y_test"
        )

    print(
        f"  Training rows  : "
        f"{len(woe_data['X_train_woe'])}"
    )

    print(
        f"  Test rows      : "
        f"{len(woe_data['X_test_woe'])}"
    )

    return binning_models, woe_data


# ============================================================================
# BIN TABLE CLEANING
# ============================================================================

def clean_binning_table(table):

    """
    Keep only actual numerical bins.

    Removes:
        Totals
        Special
        Missing

    Also converts numerical columns safely.
    """

    if table is None or table.empty:
        return pd.DataFrame()

    df = table.copy()

    if "Bin" not in df.columns:
        return pd.DataFrame()

    df["Bin"] = (
        df["Bin"]
        .astype(str)
        .str.strip()
    )

    excluded = {
        "",
        "Totals",
        "Total",
        "Special",
        "Missing",
        "Missing values",
        "Special values",
    }

    df = df[
        ~df["Bin"].isin(excluded)
    ].copy()

    numeric_columns = [
        "Count",
        "Event",
        "Non-event",
        "Event rate",
        "WoE",
        "IV",
    ]

    for col in numeric_columns:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

    required_columns = [
        "Count",
        "Event",
        "Non-event",
        "Event rate",
        "WoE",
    ]

    missing = [
        col
        for col in required_columns
        if col not in df.columns
    ]

    if missing:

        print(
            f"WARNING: Missing columns: {missing}"
        )

        return pd.DataFrame()

    df = df.dropna(
        subset=required_columns
    )

    df = df.reset_index(
        drop=True
    )

    return df


# ============================================================================
# PSI
# ============================================================================

def calculate_psi(
    train_pct,
    test_pct
):

    """
    Population Stability Index:

        PSI = (Test% - Train%)
              * ln(Test% / Train%)

    Small epsilon prevents log(0).
    """

    epsilon = 1e-6

    train_pct = max(
        float(train_pct),
        epsilon
    )

    test_pct = max(
        float(test_pct),
        epsilon
    )

    return (
        (test_pct - train_pct)
        * np.log(test_pct / train_pct)
    )


# ============================================================================
# GET BIN ASSIGNMENTS
# ============================================================================

def get_bin_assignments(
    binning_model,
    values
):

    """
    Assign raw feature values to the existing
    OptimalBinning bins.

    Uses the already fitted model.

    No refitting occurs.
    """

    values = np.asarray(
        values,
        dtype=float
    )

    try:

        transformed = binning_model.transform(
            values,
            metric="bins"
        )

        return np.asarray(
            transformed,
            dtype=object
        )

    except Exception:

        # Some versions of OptBinning expose
        # the binning table differently.
        # Fall back to the fitted splits.

        if not hasattr(
            binning_model,
            "splits"
        ):
            raise RuntimeError(
                "Unable to obtain bin assignments "
                "from OptimalBinning model."
            )

        splits = np.asarray(
            binning_model.splits,
            dtype=float
        )

        result = np.empty(
            len(values),
            dtype=object
        )

        for i, value in enumerate(values):

            if np.isnan(value):

                result[i] = "Missing"

            else:

                index = np.searchsorted(
                    splits,
                    value,
                    side="right"
                )

                if index == 0:

                    result[i] = 0

                else:

                    result[i] = index

        return result


# ============================================================================
# EVENT RATE BY BIN
# ============================================================================

def calculate_dataset_bin_statistics(
    binning_model,
    values,
    target,
    bin_labels
):

    """
    Calculate count, population percentage,
    event count and event rate for each fitted bin.
    """

    values = np.asarray(
        values,
        dtype=float
    )

    target = np.asarray(
        target,
        dtype=int
    )

    assignments = get_bin_assignments(
        binning_model,
        values
    )

    rows = []

    total = len(values)

    # Determine number of actual numerical bins.
    try:

        table = clean_binning_table(
            binning_model.binning_table.build()
        )

        n_bins = len(table)

    except Exception:

        if hasattr(
            binning_model,
            "splits"
        ):

            n_bins = (
                len(
                    binning_model.splits
                ) + 1
            )

        else:

            raise

    for bin_index in range(n_bins):

        mask = np.array(
            assignments == bin_index
        )

        count = int(
            mask.sum()
        )

        if count == 0:

            event_count = 0
            non_event_count = 0
            event_rate = np.nan
            population_pct = 0.0

        else:

            events = target[mask]

            event_count = int(
                events.sum()
            )

            non_event_count = (
                count - event_count
            )

            event_rate = (
                event_count / count
            )

            population_pct = (
                count / total
            )

        rows.append(
            {
                "bin_index": bin_index,
                "count": count,
                "population_pct": population_pct,
                "event": event_count,
                "non_event": non_event_count,
                "event_rate": event_rate,
            }
        )

    return pd.DataFrame(rows)


# ============================================================================
# ALIGN BIN STATISTICS
# ============================================================================

def add_bin_labels(
    stats,
    clean_table
):

    """
    Attach the actual OptimalBinning bin labels
    to the calculated statistics.
    """

    stats = stats.copy()

    labels = (
        clean_table["Bin"]
        .astype(str)
        .tolist()
    )

    stats["bin"] = [
        labels[i]
        if i < len(labels)
        else f"BIN_{i}"
        for i in stats["bin_index"]
    ]

    return stats


# ============================================================================
# FEATURE AUDIT
# ============================================================================

def audit_feature(
    feature,
    binning_model,
    X_train,
    y_train,
    X_test,
    y_test,
):

    print("\n" + "-" * 75)
    print(f"FEATURE: {feature}")
    print("-" * 75)

    # ------------------------------------------------------------------------
    # Get fitted bin table
    # ------------------------------------------------------------------------

    try:

        table = binning_model.binning_table.build()

    except Exception as exc:

        print(
            f"Could not build binning table: {exc}"
        )

        return []

    clean_table = clean_binning_table(
        table
    )

    if clean_table.empty:

        print(
            "No usable numerical bins found."
        )

        return []

    # ------------------------------------------------------------------------
    # Calculate train/test statistics
    # ------------------------------------------------------------------------

    train_stats = calculate_dataset_bin_statistics(
        binning_model,
        X_train,
        y_train,
        clean_table["Bin"]
    )

    test_stats = calculate_dataset_bin_statistics(
        binning_model,
        X_test,
        y_test,
        clean_table["Bin"]
    )

    train_stats = add_bin_labels(
        train_stats,
        clean_table
    )

    test_stats = add_bin_labels(
        test_stats,
        clean_table
    )

    print(
        f"\nNumber of numerical bins: "
        f"{len(clean_table)}"
    )

    print(
        "\nTrain vs Test statistics:"
    )

    results = []

    # ------------------------------------------------------------------------
    # Compare every bin
    # ------------------------------------------------------------------------

    for i in range(len(clean_table)):

        train_row = train_stats.iloc[i]
        test_row = test_stats.iloc[i]

        bin_label = train_row["bin"]

        train_count = int(
            train_row["count"]
        )

        test_count = int(
            test_row["count"]
        )

        train_pct = float(
            train_row["population_pct"]
        )

        test_pct = float(
            test_row["population_pct"]
        )

        train_event_rate = float(
            train_row["event_rate"]
        )

        test_event_rate = float(
            test_row["event_rate"]
        )

        # ------------------------------------------------------------
        # Find baseline WoE from fitted binning table
        # ------------------------------------------------------------

        baseline_row = clean_table.iloc[i]

        train_woe = float(
            baseline_row["WoE"]
        )

        # The fitted WoE is based on the training data.
        #
        # For test WoE, calculate it directly from:
        #
        #   ln(
        #       distribution of non-events /
        #       distribution of events
        #   )
        #
        # This matches the usual WoE orientation used
        # by OptimalBinning.

        total_train_events = (
            train_stats["event"].sum()
        )

        total_train_non_events = (
            train_stats["non_event"].sum()
        )

        total_test_events = (
            test_stats["event"].sum()
        )

        total_test_non_events = (
            test_stats["non_event"].sum()
        )

        train_event_dist = (
            train_row["event"]
            / max(total_train_events, 1)
        )

        train_non_event_dist = (
            train_row["non_event"]
            / max(total_train_non_events, 1)
        )

        test_event_dist = (
            test_row["event"]
            / max(total_test_events, 1)
        )

        test_non_event_dist = (
            test_row["non_event"]
            / max(total_test_non_events, 1)
        )

        epsilon = 1e-6

        test_woe = np.log(
            max(test_non_event_dist, epsilon)
            /
            max(test_event_dist, epsilon)
        )

        # ------------------------------------------------------------
        # Drift calculations
        # ------------------------------------------------------------

        population_shift = (
            test_pct - train_pct
        )

        event_rate_difference = (
            test_event_rate
            - train_event_rate
        )

        abs_event_rate_difference = abs(
            event_rate_difference
        )

        woe_difference = (
            test_woe
            - train_woe
        )

        abs_woe_difference = abs(
            woe_difference
        )

        psi = calculate_psi(
            train_pct,
            test_pct
        )

        # ------------------------------------------------------------
        # Bin size classification
        # ------------------------------------------------------------

        if (
            train_pct < MIN_BIN_PCT
            or test_pct < MIN_BIN_PCT
        ):

            size_status = "SMALL_POPULATION"

        else:

            size_status = "OK"

        # ------------------------------------------------------------
        # PSI classification
        # ------------------------------------------------------------

        if psi < PSI_STABLE:

            psi_status = "STABLE"

        elif psi < PSI_REVIEW:

            psi_status = "REVIEW"

        else:

            psi_status = "UNSTABLE"

        # ------------------------------------------------------------
        # Event-rate drift classification
        # ------------------------------------------------------------

        if (
            abs_event_rate_difference
            < EVENT_RATE_REVIEW
        ):

            event_status = "STABLE"

        elif (
            abs_event_rate_difference
            < EVENT_RATE_UNSTABLE
        ):

            event_status = "REVIEW"

        else:

            event_status = "UNSTABLE"

        # ------------------------------------------------------------
        # WoE drift classification
        # ------------------------------------------------------------

        if (
            abs_woe_difference
            < WOE_REVIEW
        ):

            woe_status = "STABLE"

        elif (
            abs_woe_difference
            < WOE_UNSTABLE
        ):

            woe_status = "REVIEW"

        else:

            woe_status = "UNSTABLE"

        # ------------------------------------------------------------
        # Overall status
        # ------------------------------------------------------------

        if (
            psi_status == "UNSTABLE"
            or event_status == "UNSTABLE"
            or woe_status == "UNSTABLE"
        ):

            overall_status = "UNSTABLE"

        elif (
            psi_status == "REVIEW"
            or event_status == "REVIEW"
            or woe_status == "REVIEW"
            or size_status == "SMALL_POPULATION"
        ):

            overall_status = "REVIEW"

        else:

            overall_status = "KEEP"

        result = {

            "feature": feature,

            "bin": bin_label,

            "train_count": train_count,
            "test_count": test_count,

            "train_population_pct": train_pct,
            "test_population_pct": test_pct,

            "population_shift": population_shift,

            "psi": psi,
            "psi_status": psi_status,

            "train_event_rate": train_event_rate,
            "test_event_rate": test_event_rate,

            "event_rate_difference":
                event_rate_difference,

            "abs_event_rate_difference":
                abs_event_rate_difference,

            "event_rate_status":
                event_status,

            "train_woe":
                train_woe,

            "test_woe":
                test_woe,

            "woe_difference":
                woe_difference,

            "abs_woe_difference":
                abs_woe_difference,

            "woe_status":
                woe_status,

            "size_status":
                size_status,

            "overall_status":
                overall_status,
        }

        results.append(
            result
        )

        # ------------------------------------------------------------
        # Console output
        # ------------------------------------------------------------

        print(
            f"\nBin: {bin_label}"
        )

        print(
            f"  Population: "
            f"{train_pct:.4f} -> "
            f"{test_pct:.4f}"
        )

        print(
            f"  PSI: "
            f"{psi:.6f} "
            f"[{psi_status}]"
        )

        print(
            f"  Event rate: "
            f"{train_event_rate:.4f} -> "
            f"{test_event_rate:.4f}"
        )

        print(
            f"  Event-rate drift: "
            f"{event_rate_difference:+.4f} "
            f"[{event_status}]"
        )

        print(
            f"  WoE: "
            f"{train_woe:.4f} -> "
            f"{test_woe:.4f}"
        )

        print(
            f"  WoE drift: "
            f"{woe_difference:+.4f} "
            f"[{woe_status}]"
        )

        print(
            f"  Overall: "
            f"{overall_status}"
        )

    return results


# ============================================================================
# FEATURE SUMMARY
# ============================================================================

def summarize_feature(
    feature,
    results
):

    if not results:

        return {
            "feature": feature,
            "bins": 0,
            "keep": 0,
            "review": 0,
            "unstable": 0,
            "max_psi": np.nan,
            "max_event_rate_drift": np.nan,
            "max_woe_drift": np.nan,
            "overall_status": "INSUFFICIENT_DATA",
        }

    df = pd.DataFrame(
        results
    )

    keep = int(
        (
            df["overall_status"]
            == "KEEP"
        ).sum()
    )

    review = int(
        (
            df["overall_status"]
            == "REVIEW"
        ).sum()
    )

    unstable = int(
        (
            df["overall_status"]
            == "UNSTABLE"
        ).sum()
    )

    max_psi = float(
        df["psi"].max()
    )

    max_event_rate_drift = float(
        df["abs_event_rate_difference"].max()
    )

    max_woe_drift = float(
        df["abs_woe_difference"].max()
    )

    if unstable > 0:

        overall_status = "UNSTABLE"

    elif review > 0:

        overall_status = "REVIEW"

    else:

        overall_status = "KEEP"

    return {

        "feature": feature,

        "bins": len(df),

        "keep": keep,
        "review": review,
        "unstable": unstable,

        "max_psi": max_psi,

        "max_event_rate_drift":
            max_event_rate_drift,

        "max_woe_drift":
            max_woe_drift,

        "overall_status":
            overall_status,
    }


# ============================================================================
# MAIN
# ============================================================================

def main():

    print("=" * 75)
    print(
        "PRISM - TRAIN vs TEST BIN STABILITY & PSI AUDIT"
    )
    print("=" * 75)

    binning_models, woe_data = (
        load_artifacts()
    )

    X_train_woe = woe_data[
        "X_train_woe"
    ]

    X_test_woe = woe_data[
        "X_test_woe"
    ]

    y_train = np.asarray(
        woe_data["y_train"]
    )

    y_test = np.asarray(
        woe_data["y_test"]
    )

    all_results = []

    summary_results = []

    print("\n" + "=" * 75)
    print(
        "TRAIN vs TEST BIN ANALYSIS"
    )
    print("=" * 75)

    # ------------------------------------------------------------------------
    # IMPORTANT:
    #
    # The WoE artifact contains transformed data, not raw feature values.
    #
    # Therefore we cannot reconstruct raw bin assignments from X_train_woe.
    #
    # Instead, this audit reconstructs the train/test bin distributions
    # from the fitted WoE values and the fitted binning table.
    #
    # Since every fitted bin maps to a WoE value, the WoE values are used
    # to identify the corresponding bin.
    # ------------------------------------------------------------------------

    for feature in FEATURES:

        if feature not in binning_models:

            print(
                f"\nWARNING: "
                f"No binning model for {feature}"
            )

            summary_results.append(
                {
                    "feature": feature,
                    "bins": 0,
                    "keep": 0,
                    "review": 0,
                    "unstable": 0,
                    "max_psi": np.nan,
                    "max_event_rate_drift": np.nan,
                    "max_woe_drift": np.nan,
                    "overall_status":
                        "INSUFFICIENT_DATA",
                }
            )

            continue

        if feature not in X_train_woe.columns:

            print(
                f"\nWARNING: "
                f"{feature} missing from X_train_woe"
            )

            summary_results.append(
                {
                    "feature": feature,
                    "bins": 0,
                    "keep": 0,
                    "review": 0,
                    "unstable": 0,
                    "max_psi": np.nan,
                    "max_event_rate_drift": np.nan,
                    "max_woe_drift": np.nan,
                    "overall_status":
                        "INSUFFICIENT_DATA",
                }
            )

            continue

        # --------------------------------------------------------------------
        # Build fitted bin table
        # --------------------------------------------------------------------

        model = binning_models[
            feature
        ]

        table = clean_binning_table(
            model.binning_table.build()
        )

        if table.empty:

            print(
                f"\nWARNING: "
                f"No numerical bins for {feature}"
            )

            continue

        # --------------------------------------------------------------------
        # Identify each train/test observation by its WoE value.
        #
        # OptimalBinning's fitted WoE values identify the corresponding bin.
        # --------------------------------------------------------------------

        train_woe = np.asarray(
            X_train_woe[feature],
            dtype=float
        )

        test_woe = np.asarray(
            X_test_woe[feature],
            dtype=float
        )

        train_values = []

        test_values = []

        train_events = []

        test_events = []

        # --------------------------------------------------------------------
        # Map each fitted WoE to a numerical bin.
        # --------------------------------------------------------------------

        for _, row in table.iterrows():

            bin_woe = float(
                row["WoE"]
            )

            # Small tolerance for floating-point representation.
            tolerance = 1e-8

            train_mask = np.isclose(
                train_woe,
                bin_woe,
                atol=tolerance,
                rtol=tolerance
            )

            test_mask = np.isclose(
                test_woe,
                bin_woe,
                atol=tolerance,
                rtol=tolerance
            )

            train_count = int(
                train_mask.sum()
            )

            test_count = int(
                test_mask.sum()
            )

            train_event = int(
                y_train[train_mask].sum()
            )

            test_event = int(
                y_test[test_mask].sum()
            )

            train_non_event = (
                train_count
                - train_event
            )

            test_non_event = (
                test_count
                - test_event
            )

            train_values.append(
                {
                    "bin":
                        str(row["Bin"]),
                    "count":
                        train_count,
                    "event":
                        train_event,
                    "non_event":
                        train_non_event,
                    "woe":
                        bin_woe,
                }
            )

            test_values.append(
                {
                    "bin":
                        str(row["Bin"]),
                    "count":
                        test_count,
                    "event":
                        test_event,
                    "non_event":
                        test_non_event,
                    "woe":
                        bin_woe,
                }
            )

        # --------------------------------------------------------------------
        # Convert to DataFrames
        # --------------------------------------------------------------------

        train_df = pd.DataFrame(
            train_values
        )

        test_df = pd.DataFrame(
            test_values
        )

        total_train = len(
            train_woe
        )

        total_test = len(
            test_woe
        )

        total_train_events = int(
            y_train.sum()
        )

        total_test_events = int(
            y_test.sum()
        )

        total_train_non_events = (
            total_train
            - total_train_events
        )

        total_test_non_events = (
            total_test
            - total_test_events
        )

        feature_results = []

        print("\n" + "-" * 75)
        print(
            f"FEATURE: {feature}"
        )
        print("-" * 75)

        print(
            f"\nNumber of numerical bins: "
            f"{len(table)}"
        )

        # --------------------------------------------------------------------
        # Per-bin comparison
        # --------------------------------------------------------------------

        for i in range(len(table)):

            train_row = train_df.iloc[i]
            test_row = test_df.iloc[i]

            bin_label = train_row[
                "bin"
            ]

            train_count = int(
                train_row["count"]
            )

            test_count = int(
                test_row["count"]
            )

            train_pct = (
                train_count
                / max(total_train, 1)
            )

            test_pct = (
                test_count
                / max(total_test, 1)
            )

            train_event_rate = (
                train_row["event"]
                / max(train_count, 1)
            )

            test_event_rate = (
                test_row["event"]
                / max(test_count, 1)
            )

            train_woe_value = float(
                train_row["woe"]
            )

            # Calculate test WoE from test distribution.
            test_event_dist = (
                test_row["event"]
                / max(
                    total_test_events,
                    1
                )
            )

            test_non_event_dist = (
                test_row["non_event"]
                / max(
                    total_test_non_events,
                    1
                )
            )

            epsilon = 1e-6

            test_woe_value = np.log(
                max(
                    test_non_event_dist,
                    epsilon
                )
                /
                max(
                    test_event_dist,
                    epsilon
                )
            )

            # ------------------------------------------------------------
            # Drift
            # ------------------------------------------------------------

            population_shift = (
                test_pct
                - train_pct
            )

            psi = calculate_psi(
                train_pct,
                test_pct
            )

            event_rate_difference = (
                test_event_rate
                - train_event_rate
            )

            abs_event_rate_difference = abs(
                event_rate_difference
            )

            woe_difference = (
                test_woe_value
                - train_woe_value
            )

            abs_woe_difference = abs(
                woe_difference
            )

            # ------------------------------------------------------------
            # PSI status
            # ------------------------------------------------------------

            if psi < PSI_STABLE:

                psi_status = "STABLE"

            elif psi < PSI_REVIEW:

                psi_status = "REVIEW"

            else:

                psi_status = "UNSTABLE"

            # ------------------------------------------------------------
            # Event-rate status
            # ------------------------------------------------------------

            if (
                abs_event_rate_difference
                < EVENT_RATE_REVIEW
            ):

                event_status = "STABLE"

            elif (
                abs_event_rate_difference
                < EVENT_RATE_UNSTABLE
            ):

                event_status = "REVIEW"

            else:

                event_status = "UNSTABLE"

            # ------------------------------------------------------------
            # WoE status
            # ------------------------------------------------------------

            if (
                abs_woe_difference
                < WOE_REVIEW
            ):

                woe_status = "STABLE"

            elif (
                abs_woe_difference
                < WOE_UNSTABLE
            ):

                woe_status = "REVIEW"

            else:

                woe_status = "UNSTABLE"

            # ------------------------------------------------------------
            # Population size
            # ------------------------------------------------------------

            if (
                train_pct < MIN_BIN_PCT
                or test_pct < MIN_BIN_PCT
            ):

                size_status = (
                    "SMALL_POPULATION"
                )

            else:

                size_status = "OK"

            # ------------------------------------------------------------
            # Overall status
            # ------------------------------------------------------------

            if (
                psi_status == "UNSTABLE"
                or event_status == "UNSTABLE"
                or woe_status == "UNSTABLE"
            ):

                overall_status = "UNSTABLE"

            elif (
                psi_status == "REVIEW"
                or event_status == "REVIEW"
                or woe_status == "REVIEW"
                or size_status
                == "SMALL_POPULATION"
            ):

                overall_status = "REVIEW"

            else:

                overall_status = "KEEP"

            result = {

                "feature":
                    feature,

                "bin":
                    bin_label,

                "train_count":
                    train_count,

                "test_count":
                    test_count,

                "train_population_pct":
                    train_pct,

                "test_population_pct":
                    test_pct,

                "population_shift":
                    population_shift,

                "psi":
                    psi,

                "psi_status":
                    psi_status,

                "train_event_rate":
                    train_event_rate,

                "test_event_rate":
                    test_event_rate,

                "event_rate_difference":
                    event_rate_difference,

                "abs_event_rate_difference":
                    abs_event_rate_difference,

                "event_rate_status":
                    event_status,

                "train_woe":
                    train_woe_value,

                "test_woe":
                    test_woe_value,

                "woe_difference":
                    woe_difference,

                "abs_woe_difference":
                    abs_woe_difference,

                "woe_status":
                    woe_status,

                "size_status":
                    size_status,

                "overall_status":
                    overall_status,
            }

            feature_results.append(
                result
            )

            all_results.append(
                result
            )

            # ------------------------------------------------------------
            # Console
            # ------------------------------------------------------------

            print(
                f"\nBin: {bin_label}"
            )

            print(
                f"  Population: "
                f"{train_pct:.4f} -> "
                f"{test_pct:.4f}"
            )

            print(
                f"  PSI: "
                f"{psi:.6f} "
                f"[{psi_status}]"
            )

            print(
                f"  Event rate: "
                f"{train_event_rate:.4f} -> "
                f"{test_event_rate:.4f}"
            )

            print(
                f"  Event-rate drift: "
                f"{event_rate_difference:+.4f} "
                f"[{event_status}]"
            )

            print(
                f"  WoE: "
                f"{train_woe_value:.4f} -> "
                f"{test_woe_value:.4f}"
            )

            print(
                f"  WoE drift: "
                f"{woe_difference:+.4f} "
                f"[{woe_status}]"
            )

            print(
                f"  Overall: "
                f"{overall_status}"
            )

        summary_results.append(
            summarize_feature(
                feature,
                feature_results
            )
        )

    # =========================================================================
    # SAVE DETAILED RESULTS
    # =========================================================================

    print("\n" + "=" * 75)
    print(
        "DETAILED AUDIT SAVED"
    )
    print("=" * 75)

    if all_results:

        audit_df = pd.DataFrame(
            all_results
        )

        audit_df.to_csv(
            OUTPUT_BIN_AUDIT,
            index=False
        )

        print(
            f"File: "
            f"{os.path.abspath(OUTPUT_BIN_AUDIT)}"
        )

        print(
            f"Rows: "
            f"{len(audit_df)}"
        )

    else:

        print(
            "No audit results generated."
        )

    # =========================================================================
    # SAVE FEATURE SUMMARY
    # =========================================================================

    summary_df = pd.DataFrame(
        summary_results
    )

    summary_df.to_csv(
        OUTPUT_FEATURE_SUMMARY,
        index=False
    )

    # =========================================================================
    # FEATURE SUMMARY
    # =========================================================================

    print("\n" + "=" * 75)
    print(
        "FEATURE SUMMARY"
    )
    print("=" * 75)

    if not summary_df.empty:

        print(
            summary_df.to_string(
                index=False
            )
        )

    print("\n" + "=" * 75)
    print(
        "INTERPRETATION"
    )
    print("=" * 75)

    for _, row in summary_df.iterrows():

        feature = row[
            "feature"
        ]

        status = row[
            "overall_status"
        ]

        print(
            f"\n{feature}:"
        )

        if status == "KEEP":

            print(
                "  Train/test behaviour is "
                "reasonably stable."
            )

            print(
                "  Keep current bins for now."
            )

        elif status == "REVIEW":

            print(
                "  Some train/test drift "
                "requires review."
            )

            print(
                "  Do not automatically "
                "merge or change bins."
            )

        elif status == "UNSTABLE":

            print(
                "  Significant train/test "
                "instability detected."
            )

            print(
                "  Investigate this feature "
                "before modifying the scorecard."
            )

        else:

            print(
                "  Insufficient data for "
                "a stability conclusion."
            )

    print("\n" + "=" * 75)
    print(
        "AUDIT COMPLETE"
    )
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
