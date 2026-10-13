"""Lookup only frozen WoE values; deliberately has no fitting routines."""
from .binning import assign_bin


def transform_feature(value, feature_spec: dict) -> tuple[int, float]:
    bin_id = assign_bin(value, feature_spec)
    try:
        return bin_id, float(feature_spec["woe_mapping"][str(bin_id)])
    except KeyError as exc:
        raise ValueError("UNMAPPABLE_FROZEN_BIN") from exc
