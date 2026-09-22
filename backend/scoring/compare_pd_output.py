from pathlib import Path
import joblib
import numpy as np

# PRISM project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

historical_path = PROJECT_ROOT / "historical_artifacts" / "pd_output.pkl"
current_path = PROJECT_ROOT / "backend" / "scoring" / "artifacts" / "pd_output.pkl"

print("Historical:", historical_path)
print("Current   :", current_path)

# Check files exist
if not historical_path.exists():
    raise FileNotFoundError(f"Historical artifact not found: {historical_path}")

if not current_path.exists():
    raise FileNotFoundError(f"Current artifact not found: {current_path}")

# Load artifacts
historical = joblib.load(historical_path)
current = joblib.load(current_path)

print("\nHistorical artifact type:", type(historical))
print("Current artifact type   :", type(current))

print("\nHistorical keys:")
print(historical.keys() if isinstance(historical, dict) else "Not a dictionary")

print("\nCurrent keys:")
print(current.keys() if isinstance(current, dict) else "Not a dictionary")

# Extract raw PD values
historical_pd = np.asarray(historical["pd_values"], dtype=float)
current_pd = np.asarray(current["raw_pd_values"], dtype=float)

print("\n===== RAW PD COMPARISON =====")

print(f"Historical count : {len(historical_pd)}")
print(f"Current count    : {len(current_pd)}")

print(f"\nHistorical mean  : {historical_pd.mean():.6f}")
print(f"Current mean     : {current_pd.mean():.6f}")

print(f"\nHistorical min   : {historical_pd.min():.6f}")
print(f"Current min      : {current_pd.min():.6f}")

print(f"\nHistorical max   : {historical_pd.max():.6f}")
print(f"Current max      : {current_pd.max():.6f}")

print(f"\nMean difference  : {current_pd.mean() - historical_pd.mean():.6f}")

# Compare element-by-element if same length
if len(historical_pd) == len(current_pd):
    difference = np.abs(current_pd - historical_pd)

    print(f"\nMaximum absolute difference : {difference.max():.6f}")
    print(f"Mean absolute difference    : {difference.mean():.6f}")
    print(f"Median absolute difference  : {np.median(difference):.6f}")
else:
    print("\nCannot perform element-by-element comparison: lengths differ.")