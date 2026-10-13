from pathlib import Path
import pandas as pd

from ingestion.rpt_ingestion import (
    ingest_rpt,
    engineer_features_from_rpt,
)
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR.parent / "data" / "real_world_Data.RPT"
OUTPUT_FILE = BASE_DIR / "data" / "validation.csv"
print(f"Reading {INPUT_FILE}...")

# Parse the RPT
df, meta = ingest_rpt(INPUT_FILE)

print(f"Rows parsed: {len(df)}")

# Engineer PRISM features
features = engineer_features_from_rpt(df)

if not features:
    raise RuntimeError("No features could be generated from the RPT.")

# Create one-row validation dataframe
validation_df = pd.DataFrame([features])

# Save
Path("data").mkdir(exist_ok=True)

validation_df.to_csv(
    OUTPUT_FILE,
    index=False,
)

print("\nGenerated validation.csv\n")
print(validation_df)

print(f"\nSaved to {OUTPUT_FILE}")