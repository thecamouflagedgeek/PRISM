"""Synthetic-only loan-obligation demonstration API; never persists records."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from features.loan_stacking_demo import SCENARIOS, scenario_result


router = APIRouter(prefix="/demo/loan-stacking", tags=["Development synthetic loan-stacking demo"])


def _require_demo_mode() -> None:
    if (os.getenv("PRISM_ENV", "").strip().lower() not in {"development", "demo"}
            or os.getenv("PRISM_DEMO_FIXTURES", "").strip().lower() != "true"):
        raise HTTPException(status_code=404, detail="Synthetic loan-stacking demo is disabled")


@router.get("")
def list_scenarios():
    _require_demo_mode()
    return {"synthetic_demo": True, "scenarios": [
        {"id": scenario_id, "label": scenario["label"]}
        for scenario_id, scenario in SCENARIOS.items()
    ]}


@router.get("/{scenario_id}")
def get_scenario(scenario_id: str):
    _require_demo_mode()
    result = scenario_result(scenario_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown synthetic scenario")
    return result
