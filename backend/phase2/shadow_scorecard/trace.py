"""Independent reconstruction from the frozen JSON specification only."""
from __future__ import annotations
import bisect
import math


def independently_reconstruct(artifact: dict, feature_values: dict) -> dict:
    order = artifact["feature_order"]
    if tuple(feature_values) != tuple(order):
        raise ValueError("Feature order/set mismatch")
    woe, bins, contributions = {}, {}, {}
    lr = artifact["logistic_regression"]
    for feature in order:
        value = float(feature_values[feature])
        if math.isnan(value) and "-1" in artifact["features"][feature]["woe_mapping"]:
            bin_id = -1
            key = "-1"
            bins[feature] = bin_id
            woe[feature] = float(artifact["features"][feature]["woe_mapping"][key])
            contributions[feature] = float(lr["coefficients"][feature]) * woe[feature]
            continue
        if not math.isfinite(value):
            raise ValueError("Invalid feature value")
        edges = [float(v) for v in artifact["features"][feature]["edges"]]
        # bisect_right over cut points is the independent right-closed mapping.
        bin_id = bisect.bisect_left(edges[1:], value)
        key = str(bin_id)
        if key not in artifact["features"][feature]["woe_mapping"]:
            raise ValueError("UNMAPPABLE_FROZEN_BIN")
        bins[feature] = bin_id
        woe[feature] = float(artifact["features"][feature]["woe_mapping"][key])
        contributions[feature] = float(lr["coefficients"][feature]) * woe[feature]
    logit = float(lr["intercept"]) + math.fsum(contributions[f] for f in order)
    pd = 1.0 / (1.0 + math.exp(-logit))
    odds = (1.0 - pd) / pd
    factor = 50.0 / math.log(2.0)
    offset = 600.0 - factor * math.log(20.0)
    score = offset + factor * math.log(odds)
    return {"bins": bins, "woe": woe, "contributions": contributions,
            "logit": logit, "pd": pd, "good_bad_odds": odds, "score": score}
