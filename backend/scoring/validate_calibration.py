from pathlib import Path
import joblib
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]

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


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def main():

    print("=" * 70)
    print("PRISM — PD CALIBRATION VALIDATION")
    print("=" * 70)

    artifact = load_artifact(CURRENT_PD)

    print("\n1. ARTIFACT")

    print("Keys:", list(artifact.keys()))

    required_keys = [
        "raw_log_odds",
        "calibrated_log_odds",
        "raw_pd_values",
        "pd_values",
    ]

    missing = [
        key for key in required_keys
        if key not in artifact
    ]

    if missing:
        print("[FAIL] Missing keys:", missing)
        return

    print("[PASS] Calibration artifact structure is valid.")

    raw_log_odds = np.asarray(
        artifact["raw_log_odds"],
        dtype=float
    )

    calibrated_log_odds = np.asarray(
        artifact["calibrated_log_odds"],
        dtype=float
    )

    raw_pd = np.asarray(
        artifact["raw_pd_values"],
        dtype=float
    )

    calibrated_pd = np.asarray(
        artifact["pd_values"],
        dtype=float
    )

    print("\n2. OBSERVATIONS")

    print("Raw log-odds :", len(raw_log_odds))
    print("Calibrated log-odds:", len(calibrated_log_odds))
    print("Raw PD       :", len(raw_pd))
    print("Calibrated PD:", len(calibrated_pd))

    if not (
        len(raw_log_odds)
        == len(calibrated_log_odds)
        == len(raw_pd)
        == len(calibrated_pd)
    ):
        print("[FAIL] Observation counts do not match.")
        return

    print("[PASS] All observation counts match.")

    print("\n3. RAW PD")

    print(
        f"Mean : {raw_pd.mean():.6f} "
        f"({raw_pd.mean() * 100:.4f}%)"
    )

    print(
        f"Min  : {raw_pd.min():.6f}"
    )

    print(
        f"Max  : {raw_pd.max():.6f}"
    )

    print("\n4. CALIBRATED PD")

    print(
        f"Mean : {calibrated_pd.mean():.6f} "
        f"({calibrated_pd.mean() * 100:.4f}%)"
    )

    print(
        f"Min  : {calibrated_pd.min():.6f}"
    )

    print(
        f"Max  : {calibrated_pd.max():.6f}"
    )

    print("\n5. CALIBRATION EFFECT")

    mean_change = (
        calibrated_pd.mean()
        - raw_pd.mean()
    )

    print(
        f"Mean PD change: "
        f"{mean_change:.6f}"
    )

    print(
        f"Mean PD change: "
        f"{mean_change * 100:.4f} percentage points"
    )

    print("\n6. LOG-ODDS TRANSFORMATION")

    # Fit:
    #
    # calibrated_log_odds =
    #     intercept + slope * raw_log_odds
    #

    slope, intercept = np.polyfit(
        raw_log_odds,
        calibrated_log_odds,
        1
    )

    predicted_calibrated_log_odds = (
        intercept
        + slope * raw_log_odds
    )

    residuals = (
        calibrated_log_odds
        - predicted_calibrated_log_odds
    )

    print(
        f"Estimated calibration slope     : "
        f"{slope:.6f}"
    )

    print(
        f"Estimated calibration intercept : "
        f"{intercept:.6f}"
    )

    print(
        f"Maximum residual                : "
        f"{np.max(np.abs(residuals)):.12f}"
    )

    print(
        f"Mean absolute residual          : "
        f"{np.mean(np.abs(residuals)):.12f}"
    )

    if np.allclose(
        calibrated_log_odds,
        predicted_calibrated_log_odds,
        atol=1e-10,
        rtol=1e-10
    ):
        print(
            "[PASS] Calibration is an affine transformation "
            "of raw log-odds."
        )
    else:
        print(
            "[INFO] Calibration is not exactly affine "
            "within tolerance."
        )

    print("\n7. PD CONSISTENCY CHECK")

    reconstructed_raw_pd = sigmoid(
        raw_log_odds
    )

    reconstructed_calibrated_pd = sigmoid(
        calibrated_log_odds
    )

    raw_pd_error = np.max(
        np.abs(raw_pd - reconstructed_raw_pd)
    )

    calibrated_pd_error = np.max(
        np.abs(
            calibrated_pd -
            reconstructed_calibrated_pd
        )
    )

    print(
        f"Maximum raw PD reconstruction error: "
        f"{raw_pd_error:.12f}"
    )

    print(
        f"Maximum calibrated PD reconstruction error: "
        f"{calibrated_pd_error:.12f}"
    )

    if raw_pd_error < 1e-10:
        print("[PASS] Raw PD matches raw log-odds.")
    else:
        print("[FAIL] Raw PD reconstruction mismatch.")

    if calibrated_pd_error < 1e-10:
        print(
            "[PASS] Calibrated PD matches calibrated log-odds."
        )
    else:
        print(
            "[FAIL] Calibrated PD reconstruction mismatch."
        )

    print("\n8. RANK PRESERVATION")

    raw_rank = np.argsort(np.argsort(raw_pd))
    calibrated_rank = np.argsort(
        np.argsort(calibrated_pd)
    )

    rank_displacement = np.abs(
        raw_rank - calibrated_rank
    )

    print(
        f"Maximum rank displacement: "
        f"{rank_displacement.max()}"
    )

    if rank_displacement.max() == 0:
        print(
            "[PASS] Calibration preserves borrower risk ordering."
        )
    else:
        print(
            "[WARNING] Calibration changes risk ordering."
        )

    print("\n9. GROUND-TRUTH STATUS")

    print(
        "[INFO] No credit-default ground-truth dataset is "
        "attached to this validation."
    )

    print(
        "[INFO] PAN/document ground_truth.csv is not used "
        "because it contains document-cleanliness labels, "
        "not the 2,000 credit-default outcomes."
    )

    print(
        "[INFO] Therefore AUC, Brier score, log loss and "
        "calibration error against ground truth are not "
        "calculated here."
    )

    print("\n10. FINAL CONCLUSION")

    print(
        "[PASS] Raw model output is preserved separately."
    )

    print(
        "[PASS] Calibration is evaluated as a separate layer."
    )

    print(
        "[PASS] No unrelated PAN/document labels are used "
        "for credit-PD validation."
    )

    print(
        "[INFO] Ground-truth performance metrics require the "
        "matching 2,000-row credit-default test labels."
    )

    print("\nNo artifacts modified.")


if __name__ == "__main__":
    main()