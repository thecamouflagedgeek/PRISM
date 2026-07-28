import sys
import os
import math
import numpy as np

sys.path.append(os.path.abspath("backend"))

from ingestion.universal_pipeline import UniversalParser
from features.bank_features import BankFeatureEngineer
from scoring.risk_scorer import compute_risk_score, _load_artifacts, _model, _binning_models, _to_score, _FEATURES, _FACTOR, _OFFSET
from services.ocr_service import get_ocr_engine

def verify_math():
    ocr_engine = get_ocr_engine()
    parser = UniversalParser(ocr_engine=ocr_engine)
    file_path = "data/real_world_Data.pdf"
    
    print("=== 1. EXTRACTION ===")
    doc_type, mapped_data, raw_text = parser.process(file_path)
    
    print("\n=== 2. FEATURE ENGINEERING ===")
    engineer = BankFeatureEngineer(mapped_data)
    features = engineer.build_features()
    for k, v in features.items():
        print(f"{k}: {v}")
        
    print("\n=== 3. WoE TRANSFORMATION ===")
    _load_artifacts()
    
    woe_dict = {}
    for col in _FEATURES:
        val = features.get(col)
        binner = _binning_models[col]
        inp = np.nan if val is None else val
        woe = float(binner.transform([inp], metric="woe")[0])
        woe_dict[col] = woe
        print(f"{col}: Raw={val} -> WoE={woe:.4f}")
        
    print("\n=== 4. LOGISTIC REGRESSION (Logit) ===")
    coefs = _model.coef_[0]
    intercept = _model.intercept_[0]
    logit = intercept
    for i, col in enumerate(_FEATURES):
        logit += coefs[i] * woe_dict[col]
        print(f"  {col}: Beta={coefs[i]:.4f} * {woe_dict[col]:.4f} = {coefs[i] * woe_dict[col]:.4f}")
    
    print(f"Computed Logit: {logit:.6f}")
    
    # from model
    import pandas as pd
    woe_df = pd.DataFrame([woe_dict])[ _FEATURES ]
    model_logit = _model.decision_function(woe_df)[0]
    print(f"Model Logit: {model_logit:.6f}")
    
    print("\n=== 5. PROBABILITY OF DEFAULT ===")
    def sigmoid(x): return 1 / (1 + math.exp(-x))
    computed_pd = sigmoid(logit)
    print(f"Computed PD: {computed_pd:.6f}")
    
    model_pd = _model.predict_proba(woe_df)[0][1]
    print(f"Model PD: {model_pd:.6f}")
    
    print("\n=== 6. SCORE SCALING ===")
    print(f"Factor: {_FACTOR:.4f}, Offset: {_OFFSET:.4f}")
    computed_score = _OFFSET - _FACTOR * model_logit
    print(f"Computed Raw Score: {computed_score:.4f}")
    print(f"Clipped Score: {_to_score(model_logit)}")
    
    print("\n=== FULL PIPELINE OUTPUT ===")
    result = compute_risk_score(features, None, None)
    print(f"Score: {result['risk_score']}")
    print(f"PD: {result['probability_of_default']}")
    print(f"Tier: {result['risk_tier']}")
    print(f"Confidence: {result['confidence']['confidence_pct']}%")

if __name__ == "__main__":
    verify_math()
