import joblib
import numpy as np

binning = joblib.load("scoring/artifacts/binning.pkl")

features = [
    "credit_debit_ratio",
    "cashflow_cv",
    "net_to_gross_ratio",
    "utility_stability",
    "min_balance",
]

for col in features:
    b = binning[col]
    print(f"\n{'='*60}")
    print(f"FEATURE: {col}")
    print(f"{'='*60}")
    print(b.binning_table.build())