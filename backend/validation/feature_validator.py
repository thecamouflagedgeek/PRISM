"""
PRISM – Feature, Binning & WoE Validator   (Parts 1, 2, 3)
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

FEATURE_SPECS: Dict[str, dict] = {
    "credit_debit_ratio": {
        "description": "Total credits / total debits over statement period",
        "expected_min": 0.0, "expected_max": 10.0,
        "outlier_fence": 5.0, "missing_threshold": 0.15,
        "direction": "higher_better",
    },
    "cashflow_cv": {
        "description": "Coefficient of variation of monthly net cashflow",
        "expected_min": 0.0, "expected_max": 5.0,
        "outlier_fence": 3.0, "missing_threshold": 0.15,
        "direction": "lower_better",
    },
    "net_to_gross_ratio": {
        "description": "Net salary / gross salary",
        "expected_min": 0.3, "expected_max": 1.0,
        "outlier_fence": None, "missing_threshold": 0.30,
        "direction": "higher_better",
    },
    "utility_stability": {
        "description": "Proportion of months with on-time utility payments",
        "expected_min": 0.0, "expected_max": 1.0,
        "outlier_fence": None, "missing_threshold": 0.40,
        "direction": "higher_better",
    },
    "min_balance": {
        "description": "Minimum end-of-day balance over last 3 months",
        "expected_min": -1_000_000, "expected_max": 10_000_000,
        "outlier_fence": 500_000, "missing_threshold": 0.10,
        "direction": "higher_better",
    },
}
FEATURES = list(FEATURE_SPECS.keys())


@dataclass
class FeatureReport:
    feature: str
    n: int
    missing_rate: float
    mean: float; std: float; min: float
    p25: float; p50: float; p75: float; max: float
    outlier_rate: float
    range_violations: int
    skewness: float; kurtosis: float
    psi: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    passed: bool = True


def compute_psi(expected: pd.Series, actual: pd.Series, n_bins: int = 10) -> float:
    """PSI < 0.10 stable | 0.10–0.25 monitor | > 0.25 significant drift"""
    expected, actual = expected.dropna(), actual.dropna()
    if len(expected) == 0 or len(actual) == 0:
        return np.nan
    breakpoints = np.unique(np.nanpercentile(expected, np.linspace(0, 100, n_bins + 1)))
    if len(breakpoints) < 3:
        return np.nan
    def _bucket(s):
        c, _ = np.histogram(s, bins=breakpoints)
        p = c / len(s)
        return np.where(p == 0, 1e-4, p)
    e, a = _bucket(expected), _bucket(actual)
    n = min(len(e), len(a))
    return float(np.sum((a[:n] - e[:n]) * np.log(a[:n] / e[:n])))


def validate_features(df: pd.DataFrame, reference_df: Optional[pd.DataFrame] = None) -> Dict[str, FeatureReport]:
    reports = {}
    for feat in FEATURES:
        spec = FEATURE_SPECS[feat]
        if feat not in df.columns:
            reports[feat] = FeatureReport(feat, 0, 1.0, *[np.nan]*9, 0, np.nan, np.nan,
                                          warnings=[f"'{feat}' not in dataset"], passed=False)
            continue
        col = df[feat].dropna()
        n_total, n_valid = len(df), len(col)
        missing_rate = 1 - n_valid / n_total if n_total else 1.0
        w, passed = [], True
        if missing_rate > spec["missing_threshold"]:
            w.append(f"Missing {missing_rate:.1%} > threshold {spec['missing_threshold']:.1%}")
            passed = False
        lo, hi = spec["expected_min"], spec["expected_max"]
        range_violations = int(((col < lo) | (col > hi)).sum())
        if range_violations:
            w.append(f"{range_violations} values outside [{lo}, {hi}]")
        if spec["outlier_fence"] is not None:
            out_mask = col.abs() > spec["outlier_fence"]
        else:
            q1, q3 = col.quantile(0.25), col.quantile(0.75)
            iqr = q3 - q1
            out_mask = (col < q1 - 3*iqr) | (col > q3 + 3*iqr)
        outlier_rate = float(out_mask.mean()) if len(col) else 0.0
        if outlier_rate > 0.05:
            w.append(f"Outlier rate {outlier_rate:.1%}")
        skewness = float(col.skew()) if len(col) > 3 else np.nan
        kurtosis = float(col.kurt()) if len(col) > 3 else np.nan
        if abs(skewness) > 3:
            w.append(f"High skewness {skewness:.2f}")
        psi = None
        if reference_df is not None and feat in reference_df.columns:
            psi = compute_psi(reference_df[feat], df[feat])
            if not np.isnan(psi):
                if psi > 0.25:
                    w.append(f"PSI={psi:.3f} SIGNIFICANT DRIFT"); passed = False
                elif psi > 0.10:
                    w.append(f"PSI={psi:.3f} minor drift")
        stats_vals = [float(col.quantile(q)) if len(col) else np.nan for q in [0.25, 0.50, 0.75]]
        reports[feat] = FeatureReport(
            feature=feat, n=n_valid, missing_rate=missing_rate,
            mean=float(col.mean()) if len(col) else np.nan,
            std=float(col.std())   if len(col) else np.nan,
            min=float(col.min())   if len(col) else np.nan,
            p25=stats_vals[0], p50=stats_vals[1], p75=stats_vals[2],
            max=float(col.max())   if len(col) else np.nan,
            outlier_rate=outlier_rate, range_violations=range_violations,
            skewness=skewness, kurtosis=kurtosis, psi=psi, warnings=w, passed=passed,
        )
    return reports


@dataclass
class BinReport:
    feature: str
    n_bins: int; iv: float; monotonic: bool
    min_bin_count: int; empty_bins: int
    woe_values: List[float]
    warnings: List[str] = field(default_factory=list)
    passed: bool = True


def validate_binning(binning_models: dict) -> Dict[str, BinReport]:
    reports = {}
    for feat, binner in binning_models.items():
        w, passed = [], True
        try:
            bt = binner.binning_table.build()
        except Exception as e:
            reports[feat] = BinReport(feat, 0, 0.0, False, 0, 0, [],
                                      warnings=[str(e)], passed=False)
            continue
        data_bins = bt[~bt["Bin"].astype(str).isin(["Special", "Missing", "Totals"])]
        woe_vals  = data_bins["WoE"].tolist()
        counts    = data_bins["Count"].tolist()
        n_bins    = len(data_bins)
        empty_bins = int((data_bins["Count"] == 0).sum())
        iv = float(bt["IV"].iloc[-1]) if "IV" in bt.columns else 0.0
        monotonic = (
            all(woe_vals[i] <= woe_vals[i+1] for i in range(len(woe_vals)-1)) or
            all(woe_vals[i] >= woe_vals[i+1] for i in range(len(woe_vals)-1))
        ) if len(woe_vals) > 1 else True
        min_bin_count = int(min(counts)) if counts else 0
        if iv < 0.02:
            w.append(f"IV={iv:.4f} near-zero predictive power"); passed = False
        if iv > 0.50:
            w.append(f"IV={iv:.4f} very high — check leakage")
        if not monotonic:
            w.append("Non-monotonic WoE — bins may be unstable")
        if empty_bins:
            w.append(f"{empty_bins} empty bin(s)"); passed = False
        if min_bin_count < 20:
            w.append(f"Min bin count={min_bin_count} too small")
        if n_bins > 8:
            w.append(f"{n_bins} bins — consider max_n_bins=5")
        reports[feat] = BinReport(feat, n_bins, iv, monotonic, min_bin_count,
                                  empty_bins, [round(v, 4) for v in woe_vals], w, passed)
    return reports


@dataclass
class WoETestResult:
    feature: str
    input_value: float
    woe_output: float
    passed: bool
    note: str = ""


def validate_woe_transform(binning_models: dict) -> List[WoETestResult]:
    test_cases = {
        "credit_debit_ratio": [0.0, 0.5, 1.0, 2.0, 5.0, np.nan],
        "cashflow_cv":         [0.0, 0.3, 0.8, 1.5, 3.0, np.nan],
        "net_to_gross_ratio":  [0.4, 0.6, 0.75, 0.9, 1.0, np.nan],
        "utility_stability":   [0.0, 0.25, 0.5, 0.75, 1.0, np.nan],
        "min_balance":         [-50000, 0, 5000, 50000, 200000, np.nan],
    }
    results = []
    for feat, values in test_cases.items():
        if feat not in binning_models:
            results.append(WoETestResult(feat, np.nan, np.nan, False, "Binner not found"))
            continue
        binner = binning_models[feat]
        for val in values:
            try:
                inp = np.nan if (val is None or (isinstance(val, float) and np.isnan(val))) else val
                woe = float(binner.transform([inp], metric="woe")[0])
                ok  = np.isfinite(woe)
                results.append(WoETestResult(feat, float(val) if not np.isnan(float(val if val is not None else np.nan)) else np.nan,
                                              round(woe, 4), ok,
                                              "OK" if ok else "Non-finite WoE"))
            except Exception as e:
                results.append(WoETestResult(feat, float(val) if val is not None else np.nan,
                                              np.nan, False, str(e)))
    return results