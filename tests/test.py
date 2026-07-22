
from backend.scoring import risk_scorer as engine
engine._load_artifacts()

bank    = {...}   # paste the real feature dict that produced the 300
salary  = None    # or whatever was actually missing
utility = {...}

feature_dict = engine._map_features(bank, salary, utility)
X_woe = engine._woe_transform(feature_dict)
print(feature_dict)
print(X_woe)