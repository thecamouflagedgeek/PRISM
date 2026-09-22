from pathlib import Path
import joblib
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]

HISTORICAL_PD = (
    PROJECT_ROOT
    / "historical_artifacts"
    / "pd_output.pkl"
)

CURRENT_PD = (
    PROJECT_ROOT
    / "backend"
    / "scoring"
    / "artifacts"
    / "pd_output.pkl"
)


def load_artifact(path):
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")

    return joblib.load(path)


def describe(name, values):
    values = np.asarray(values, dtype=float)

    print(f"{name}:")
    print(f"  Count : {len(values)}")
    print(f"  Mean  : {values.mean():.6f}")
    print(f"  Min   : {values.min():.6f}")
    print(f"  Max   : {values.max():.6f}")
    print(f"  Median: {np.median(values):.6f}")
    print()


def main():

    print("=" * 70)
    print("PRISM — BASELINE MODEL REPRODUCTION AUDIT")
    print("=" * 70)

    print("\n1. FILE VALIDATION")

    historical = load_artifact(HISTORICAL_PD)
    current = load_artifact(CURRENT_PD)

    print("[PASS] Historical PD artifact found.")
    print("[PASS] Current PD artifact found.")

    print("\n2. ARTIFACT STRUCTURE")

    print("Historical keys:", list(historical.keys()))
    print("Current keys   :", list(current.keys()))

    # Historical artifact contains:
    # log_odds
    # pd_values

    # Current artifact contains:
    # raw_log_odds
    # calibrated_log_odds
    # raw_pd_values
    # pd_values

    historical_log_odds = np.asarray(
        historical["log_odds"],
        dtype=float
    )

    historical_pd = np.asarray(
        historical["pd_values"],
        dtype=float
    )

    current_raw_log_odds = np.asarray(
        current["raw_log_odds"],
        dtype=float
    )

    current_raw_pd = np.asarray(
        current["raw_pd_values"],
        dtype=float
    )

    print("\n3. OBSERVATION COUNTS")

    print(
        f"Historical observations : {len(historical_pd)}"
    )

    print(
        f"Current raw observations: {len(current_raw_pd)}"
    )

    if len(historical_pd) != len(current_raw_pd):
        print("[FAIL] Observation counts do not match.")
        return

    print("[PASS] Observation counts match.")

    print("\n4. RAW LOG-ODDS REPRODUCTION")

    log_odds_diff = np.abs(
        historical_log_odds -
        current_raw_log_odds
    )

    print(
        f"Maximum absolute difference: "
        f"{log_odds_diff.max():.12f}"
    )

    if np.allclose(
        historical_log_odds,
        current_raw_log_odds,
        atol=1e-10,
        rtol=1e-10
    ):
        print("[PASS] Raw log-odds reproduced exactly.")
    else:
        print("[FAIL] Raw log-odds do not match.")

    print("\n5. RAW PD REPRODUCTION")

    pd_diff = np.abs(
        historical_pd -
        current_raw_pd
    )

    print(
        f"Maximum absolute difference: "
        f"{pd_diff.max():.12f}"
    )

    print(
        f"Mean absolute difference   : "
        f"{pd_diff.mean():.12f}"
    )

    if np.allclose(
        historical_pd,
        current_raw_pd,
        atol=1e-10,
        rtol=1e-10
    ):
        print("[PASS] Raw PD reproduced exactly.")
    else:
        print("[FAIL] Raw PD does not match.")

    print("\n6. HISTORICAL RAW PD")

    describe(
        "Historical raw PD",
        historical_pd
    )

    print("7. CURRENT RAW PD")

    describe(
        "Current raw PD",
        current_raw_pd
    )

    print("\n8. FINAL CONCLUSION")

    if (
        np.allclose(
            historical_log_odds,
            current_raw_log_odds,
            atol=1e-10,
            rtol=1e-10
        )
        and
        np.allclose(
            historical_pd,
            current_raw_pd,
            atol=1e-10,
            rtol=1e-10
        )
    ):
        print(
            "[PASS] Historical and current raw model outputs "
            "are identical."
        )
        print(
            "[PASS] Logistic Regression / WoE model reproduction "
            "is validated."
        )
        print(
            "[INFO] Any difference in final PD values is caused "
            "by the calibration layer."
        )
    else:
        print(
            "[FAIL] Raw model reproduction could not be validated."
        )

    print("\nNo artifacts modified.")


if __name__ == "__main__":
    main()