"""Load and validate the serialized Phase 2B.6 scorecard without fitting."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

PHASE2 = Path(__file__).resolve().parents[1]
RECOVERED = PHASE2 / "outputs" / "phase2b6_recovery" / "recovered_final_scorecard.json"
OUTPUT = PHASE2 / "outputs" / "phase2f"
FEATURE_ORDER = [
    "recent_delinquency_level",
    "months_with_delinquency",
    "payment_to_statement_ratio",
    "mean_statement_balance",
]


def load_scorecard(path: Path = RECOVERED) -> dict:
    raw = path.read_bytes()
    artifact = json.loads(raw)
    if artifact.get("artifact_type") != "EXPERIMENTAL_RECOVERED_PHASE_2B6_SCORECARD":
        raise ValueError("Unexpected frozen scorecard artifact type")
    if artifact.get("source_status") != "PHASE_2B6_INCONCLUSIVE":
        raise ValueError("Frozen source status mismatch")
    if artifact.get("feature_order") != FEATURE_ORDER:
        raise ValueError("Frozen feature order mismatch")
    lr = artifact.get("logistic_regression", {})
    if lr.get("feature_order") != FEATURE_ORDER or set(lr.get("coefficients", {})) != set(FEATURE_ORDER):
        raise ValueError("Frozen coefficient order or names mismatch")
    for name in FEATURE_ORDER:
        spec = artifact["features"].get(name)
        edges = spec["edges"]
        if not edges or len(edges) < 2 or len(edges) != len(spec["woe_mapping"]) + (1 if "-1" not in spec["woe_mapping"] else 2):
            # Edges count numeric bins + 1; a separate -1 missing bin has no edge.
            numeric_bins = sum(1 for k in spec["woe_mapping"] if int(k) >= 0)
            if len(edges) != numeric_bins + 1:
                raise ValueError(f"Invalid frozen bin edges: {name}")
        if not spec.get("right_closed") or not spec.get("include_lowest"):
            raise ValueError(f"Unsupported interval semantics: {name}")
        for key, val in spec["woe_mapping"].items():
            if not math.isfinite(float(val)):
                raise ValueError(f"Non-finite frozen WoE: {name}:{key}")
    artifact["artifact_sha256"] = hashlib.sha256(raw).hexdigest().upper()
    return artifact
