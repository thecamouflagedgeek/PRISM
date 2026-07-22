import sys
import os

# Add backend to path
sys.path.append(os.path.abspath("backend"))

from ingestion.universal_pipeline import UniversalParser
from features.bank_features import BankFeatureEngineer

from services.ocr_service import get_ocr_engine

file_path = "data/real_world_Data.pdf"

try:
    print(f"Processing {file_path}...")
    ocr_engine = get_ocr_engine()
    parser = UniversalParser(ocr_engine=ocr_engine)
    doc_type, mapped_data, raw_text = parser.process(file_path)
    print(f"Document Type: {doc_type}")
    print("Mapped Data (First 5 rows):")
    print(mapped_data.head() if hasattr(mapped_data, "head") else mapped_data)
    
    if doc_type == "BANK":
        print("\n--- Engineering Features ---")
        print("Raw dates:", repr(mapped_data["date"].tolist()[:10]))
        engineer = BankFeatureEngineer(mapped_data)
        print("Engineer DataFrame:")
        print(engineer.df[["date", "month", "amount", "type"]].head())
        print(engineer.df.dtypes)
        features = engineer.build_features()
        print("\nFeatures:")
        for k, v in features.items():
            print(f"  {k}: {v}")
            
except Exception as e:
    import traceback
    traceback.print_exc()
