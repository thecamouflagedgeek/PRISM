from scoring.risk_scorer import score_borrower


result = score_borrower(
    bank={
        "credit_debit_ratio": 1.25,
        "cashflow_cv": 0.35,
        "min_balance_l3m": 25000,
    },
    salary={
        "net_to_gross_ratio": 0.82,
    },
    utility={
        "utility_stability": 0.20,
    },
)


print("\n========== PRISM RISK RESULT ==========")

print("Score:", result["score"])
print("PD:", result["pd"])
print("Risk Tier:", result["risk_tier"])
print("Log Odds:", result["log_odds"])

print("\nRaw Features:")
for k, v in result["features"].items():
    print(f"  {k}: {v}")

print("\nWoE Features:")
for k, v in result["woe_features"].items():
    print(f"  {k}: {v}")

print("\nFeature Contributions:")
for k, v in result["feature_contributions"].items():
    print(f"  {k}: {v}")

print("\nReason Codes:")
for reason in result["reason_codes"]:
    print(" ", reason)

print("\nConfidence:")
print(result["confidence"])

print("\n========================================")