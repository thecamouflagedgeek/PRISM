"""Manual scorer smoke script; excluded from test discovery side effects."""
from scoring.risk_scorer import score_borrower


def main():
    result = score_borrower(
        bank={"credit_debit_ratio": 1.25, "cashflow_cv": 0.35, "min_balance_l3m": 25000},
        salary={"net_to_gross_ratio": 0.82},
        utility={"utility_stability": 0.20},
    )
    print("Status:", result["status"])
    print("Display score:", result["display_score"])
    print("Raw uncalibrated PD:", result["raw_pd"])
    print("Feature states:", result["feature_states"])
    if result["status"] == "SCORED":
        print("Log odds:", result["log_odds"])
        print("WoE:", result["woe_features"])
        print("Scorecard reason codes:", result["reason_codes"])
    else:
        print("No score returned: validated document evidence was not supplied.")


if __name__ == "__main__":
    main()
