"""Frozen Phase 2B.6 interval assignment; no bin learning occurs here."""
from __future__ import annotations
import math
import numpy as np


class UnmappableFrozenBin(ValueError):
    pass


def assign_bin(value, feature_spec: dict) -> int:
    if value is None:
        raise UnmappableFrozenBin("MISSING_FEATURE")
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise UnmappableFrozenBin("INVALID_FEATURE") from exc
    if math.isnan(x):
        if "-1" in feature_spec["woe_mapping"]:
            return -1
        raise UnmappableFrozenBin("UNMAPPABLE_FROZEN_BIN")
    if not math.isfinite(x):
        raise UnmappableFrozenBin("INVALID_FEATURE")
    edges = feature_spec["edges"]
    # np.digitize(..., right=True) matches pandas cut right=True: (a,b],
    # with the first interval including its lower endpoint.
    numeric_edges = np.asarray([float(v) for v in edges], dtype=float)
    idx = int(np.searchsorted(numeric_edges[1:], x, side="left"))
    if idx < 0 or idx >= len(numeric_edges) - 1:
        raise UnmappableFrozenBin("UNMAPPABLE_FROZEN_BIN")
    key = str(idx)
    if key not in feature_spec["woe_mapping"]:
        raise UnmappableFrozenBin("UNMAPPABLE_FROZEN_BIN")
    return idx
