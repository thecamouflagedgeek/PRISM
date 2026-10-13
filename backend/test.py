from scoring.risk_scorer import _load_artifacts, _map_features, _woe_transform
_load_artifacts()

# paste the real bank/salary/utility dicts for the applicant that scored 300
feature_dict = _map_features(bank, salary, utility)
X_woe = _woe_transform(feature_dict)
print(feature_dict)
print(X_woe)