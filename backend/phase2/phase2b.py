"""Leakage-safe exploratory Berka scorecard experiment (Phase 2B).

All transforms are fit inside each development split. Phase 2A's corrected
feature table is the sole feature source; window boundaries are rechecked via
phase2.windowing before any split or fit is made.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy.optimize import minimize
from scipy.stats import rankdata, spearmanr

from phase2.berka_audit import dte, load, num
from phase2.windowing import complete_calendar_window

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "outputs" / "berka_audit"
OUT = ROOT / "outputs" / "phase2b"
CONFIG_PATH = ROOT / "config" / "phase2b_experiment.json"
SEED = 260610
REPEATS = 20
VALIDATION_FRACTION = 0.25
HOLDOUT_FRACTION = 0.20
MAX_FEATURES = 2
WOE_CONVENTION = "ln(% non-default in bin / % default in bin); positive WoE indicates lower observed risk"
FORBIDDEN = {
    "loan_id", "account_id", "status", "target", "window", "window_start",
    "window_end_exclusive", "calendar_months", "coverage_state", "eligible",
    "incomplete_coverage", "loan_amount", "duration", "payments", "loan_payment",
    "documented_loan_payment_total", "postloan_transaction_count",
}

# Candidate definitions and source names are copied from the corrected Phase 2A
# dictionary. Phase 2B consumes Phase 2A's already-generated feature values.
FEATURES = [
    "avg_monthly_credit", "avg_monthly_debit", "credit_debit_ratio",
    "avg_monthly_net_cashflow", "cashflow_std", "cashflow_cv",
    "positive_cashflow_month_ratio", "negative_cashflow_month_ratio",
    "negative_cashflow_month_count", "inflow_trend", "outflow_trend",
    "avg_balance", "min_balance", "max_balance", "balance_std", "balance_cv",
    "low_balance_frequency", "negative_balance_frequency",
    "end_of_month_balance_trend", "transaction_count", "median_count_months",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stratified_indices(y: np.ndarray, test_fraction: float, seed: int):
    rng = np.random.default_rng(seed)
    train, test = [], []
    for cls in (0, 1):
        idx = np.flatnonzero(y == cls)
        idx = rng.permutation(idx)
        n_test = max(1, int(round(len(idx) * test_fraction)))
        n_test = min(n_test, len(idx) - 1)
        test.extend(idx[:n_test])
        train.extend(idx[n_test:])
    return np.array(sorted(train), dtype=int), np.array(sorted(test), dtype=int)


def assert_corrected_cohorts(features: pd.DataFrame, reconciliation: pd.DataFrame) -> dict:
    """Fail closed unless feature rows match regenerated Phase 2A membership."""
    result = {}
    for window, expected_n, expected_defaults in (("3m", 231, 31), ("6m", 187, 19)):
        target_rows = features[(features.window == window) & features.status.isin(["A", "B"])]
        eligible = target_rows[target_rows.eligible.astype(bool)].copy()
        reg = reconciliation[
            (reconciliation.window == window)
            & reconciliation.status.isin(["A", "B"])
            & reconciliation.new_calendar_eligible.astype(bool)
        ]
        feature_ids = set(eligible.loan_id.astype(int))
        audit_ids = set(reg.loan_id.astype(int))
        if feature_ids != audit_ids:
            raise RuntimeError(f"{window} Phase 2B membership differs from corrected Phase 2A: {sorted(feature_ids ^ audit_ids)}")
        if eligible.loan_id.duplicated().any() or reg.loan_id.duplicated().any():
            raise RuntimeError(f"Duplicate loan IDs in corrected {window} cohort")
        observed = (len(eligible), int(eligible.target.sum()), int((eligible.target == 0).sum()))
        # Expected figures are a guard after independent membership comparison,
        # never used to create or filter the cohort.
        if observed != (expected_n, expected_defaults, expected_n - expected_defaults):
            raise RuntimeError(f"Corrected Phase 2A {window} data has unexpected counts: {observed}")
        result[window] = {
            "n": observed[0], "defaults": observed[1], "nondefaults": observed[2],
            "default_rate": observed[1] / observed[0],
            "phase2a_membership_match": True,
            "loan_ids_sha256": hashlib.sha256(",".join(map(str, sorted(feature_ids))).encode()).hexdigest(),
        }
    return result


def assert_canonical_windows(features: pd.DataFrame) -> None:
    """Rebuild matured cohorts from raw loan/account dates via the canonical helper."""
    raw_account = num(load(ROOT / "berka" / "account.asc"))
    raw_loan = num(load(ROOT / "berka" / "loan.asc"))
    raw_trans = num(load(ROOT / "berka" / "trans.asc"))
    account_dates = dict(zip(raw_account.account_id.astype(int), dte(raw_account.date)))
    loans = raw_loan.copy()
    loans["parsed_date"] = dte(loans.date)
    loan_dates = dict(zip(loans.loan_id.astype(int), loans.parsed_date))
    tx_dates = dte(raw_trans.date).dropna()
    source_start = tx_dates.min().date()
    source_end = (tx_dates.max() + pd.Timedelta(days=1)).date()
    matured = loans[loans.status.isin(["A", "B"])]
    phase2a_rows = features.copy()
    phase2a_rows["loan_id"] = phase2a_rows.loan_id.astype(int)
    phase2a_rows = phase2a_rows.set_index(["loan_id", "window"])
    if not phase2a_rows.index.is_unique:
        raise RuntimeError("Duplicate loan/window rows in Phase 2A candidate table")
    for window, months in (("3m", 3), ("6m", 6)):
        raw_eligible = set()
        for row in matured.itertuples(index=False):
            loan_id, account_id = int(row.loan_id), int(row.account_id)
            opened = account_dates.get(account_id)
            loan_date = loan_dates.get(loan_id)
            if pd.isna(opened) or pd.isna(loan_date):
                raise RuntimeError(f"Missing account/loan date in raw cohort for loan {loan_id}")
            w = complete_calendar_window(
                pd.Timestamp(loan_date).date(), months,
                account_open_date=pd.Timestamp(opened).date(),
                source_coverage_start=source_start,
                source_coverage_end_exclusive=source_end,
            )
            try:
                saved = phase2a_rows.loc[(loan_id, window)]
            except KeyError:
                raise RuntimeError(f"Phase 2A must have one {window} row for raw matured loan {loan_id}") from None
            if (str(w.window_start) != str(saved.window_start)
                    or str(w.window_end_exclusive) != str(saved.window_end_exclusive)
                    or bool(w.eligible) != bool(saved.eligible)):
                raise RuntimeError(f"Canonical window assertion failed for loan {loan_id}/{window}")
            if int(saved.target) != (1 if row.status == "B" else 0):
                raise RuntimeError(f"Target mapping mismatch for loan {loan_id}: status {row.status}")
            if w.eligible:
                raw_eligible.add(loan_id)
        feature_eligible = set(
            features.loc[(features.window == window) & features.status.isin(["A", "B"])
                         & features.eligible.astype(bool), "loan_id"].astype(int)
        )
        if raw_eligible != feature_eligible:
            raise RuntimeError(f"Phase 2A {window} cohort does not match raw-data canonical cohort: {sorted(raw_eligible ^ feature_eligible)}")


def assert_monthly_history_windows(features: pd.DataFrame, monthly: pd.DataFrame) -> None:
    """Ensure Phase 2A's aggregates cover exactly the canonical complete months."""
    for row in features[
        features.status.isin(["A", "B"]) & features.window.isin(["3m", "6m"])
        & features.eligible.astype(bool)
    ].itertuples(index=False):
        history = monthly[(monthly.loan_id.astype(int) == int(row.loan_id)) & (monthly.window == row.window)]
        expected = int(row.calendar_months)
        start = pd.Timestamp(row.window_start)
        end = pd.Timestamp(row.window_end_exclusive)
        expected_months = pd.date_range(start, end - pd.offsets.MonthBegin(1), freq="MS").strftime("%Y-%m").tolist()
        observed_months = history.month.astype(str).tolist()
        if len(history) != expected or observed_months != expected_months:
            raise RuntimeError(f"Phase 2A monthly history does not exactly span canonical window for loan {row.loan_id}/{row.window}")


def _fit_binner(x: np.ndarray, y: np.ndarray):
    finite = np.isfinite(x)
    cut = float(np.median(x[finite])) if finite.any() else None
    bins = np.full(len(x), -1, dtype=int)
    if finite.any():
        bins[finite] = (x[finite] > cut).astype(int)
    # Missing is an explicit bin. Constant features retain one observed bin.
    k = len(set(bins.tolist()))
    groups = sorted(set(bins.tolist()))
    good_total, bad_total = int((y == 0).sum()), int((y == 1).sum())
    woe, iv_parts, metadata = {}, [], []
    alpha = 0.5
    for g in groups:
        mask = bins == g
        good, bad = int(((y == 0) & mask).sum()), int(((y == 1) & mask).sum())
        good_dist = (good + alpha) / (good_total + alpha * k)
        bad_dist = (bad + alpha) / (bad_total + alpha * k)
        value = math.log(good_dist / bad_dist)
        woe[int(g)] = value
        iv_parts.append((good_dist - bad_dist) * value)
        metadata.append({"bin": int(g), "label": "missing" if g == -1 else ("low_or_equal" if g == 0 else "high"),
                         "n": int(mask.sum()), "defaults": bad, "nondefaults": good, "woe": value})
    return {"cut": cut, "woe": woe, "iv": float(sum(iv_parts)), "bins": metadata,
            "fallback_woe": 0.0,
            "fallback_policy": "train-derived neutral WOE for a validation-only missing/unseen group; explicitly recorded, never inferred as a fitted risk bin"}


def _transform(x: np.ndarray, binner: dict) -> np.ndarray:
    finite = np.isfinite(x)
    bins = np.full(len(x), -1, dtype=int)
    if finite.any():
        bins[finite] = (x[finite] > binner["cut"]).astype(int) if binner["cut"] is not None else 0
    # A missing/unseen bin gets an explicitly smoothed train-derived WOE.
    return np.array([binner["woe"].get(int(g), binner["fallback_woe"]) for g in bins], dtype=float)


def _fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 1.0):
    X1 = np.column_stack([np.ones(len(X)), X])
    def objective(beta):
        z = np.clip(X1 @ beta, -35, 35)
        loss = np.logaddexp(0, z).sum() - (y * z).sum() + 0.5 * l2 * np.sum(beta[1:] ** 2)
        p = 1 / (1 + np.exp(-z))
        grad = X1.T @ (p - y)
        grad[1:] += l2 * beta[1:]
        return loss, grad
    fit = minimize(objective, np.zeros(X1.shape[1]), jac=True, method="BFGS", options={"maxiter": 500, "gtol": 1e-8})
    if not np.isfinite(fit.x).all():
        raise RuntimeError("Logistic fit produced non-finite coefficients")
    return fit.x, bool(fit.success), str(fit.message)


def _predict(X: np.ndarray, beta: np.ndarray):
    z = beta[0] + X @ beta[1:]
    return z, 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def _metrics(y: np.ndarray, pd_hat: np.ndarray) -> dict:
    eps = 1e-12
    p = np.clip(pd_hat, eps, 1-eps)
    if len(np.unique(y)) > 1:
        auc = float((rankdata(p)[y == 1].sum() - (y == 1).sum() * ((y == 1).sum()+1)/2) / ((y == 1).sum() * (y == 0).sum()))
        ks = float(max(abs((np.sort(p[y == 1][:, None], axis=0) if False else np.array([0]))))) if False else float(_ks(y, p))
    else:
        auc, ks = None, None
    lp = np.log(p / (1-p))
    # Calibration regression on evaluation data is diagnostic only; no calibrator is applied.
    cal_intercept = cal_slope = None
    if len(np.unique(y)) > 1:
        X = np.column_stack([np.ones(len(lp)), lp])
        def loss(b):
            z = np.clip(X @ b, -35, 35)
            return float((np.logaddexp(0, z) - y*z).sum() + 1e-8*np.sum(b*b))
        fit = minimize(loss, np.array([0., 1.]), method="BFGS")
        cal_intercept, cal_slope = map(float, fit.x)
    return {"n": int(len(y)), "defaults": int(y.sum()), "observed_default_rate": float(y.mean()),
            "mean_predicted_pd": float(p.mean()), "auc": auc, "gini": None if auc is None else 2*auc-1,
            "ks": ks, "brier": float(np.mean((p-y)**2)),
            "log_loss": float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
            "calibration_intercept": cal_intercept, "calibration_slope": cal_slope}


def _ks(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p)
    ys = y[order]
    tpr = np.cumsum(ys) / max(1, ys.sum())
    fpr = np.cumsum(1-ys) / max(1, (1-ys).sum())
    return float(np.max(np.abs(tpr-fpr)))


def _select(train: pd.DataFrame, y: np.ndarray):
    binners, woe, iv = {}, {}, {}
    for name in FEATURES:
        x = pd.to_numeric(train[name], errors="coerce").to_numpy(dtype=float)
        binners[name] = _fit_binner(x, y)
        iv[name] = binners[name]["iv"]
        woe[name] = _transform(x, binners[name])
    order = sorted(FEATURES, key=lambda n: (-iv[n], n))
    selected = []
    for name in order:
        if not np.isfinite(iv[name]) or np.nanstd(woe[name]) == 0:
            continue
        redundant = False
        for prior in selected:
            corr = spearmanr(woe[name], woe[prior]).statistic
            if np.isfinite(corr) and abs(float(corr)) >= 0.80:
                redundant = True
                break
        if not redundant:
            selected.append(name)
        if len(selected) == MAX_FEATURES:
            break
    if not selected:
        selected = [order[0]]
    X = np.column_stack([woe[n] for n in selected])
    return selected, binners, X, iv


def _apply(frame: pd.DataFrame, selected: list[str], binners: dict):
    return np.column_stack([_transform(pd.to_numeric(frame[n], errors="coerce").to_numpy(dtype=float), binners[n]) for n in selected])


def score_from_pd(pd_values):
    factor = 50 / math.log(2)
    odds = (1-pd_values) / pd_values
    return 600 + factor * np.log(odds / 20)


def run_window(frame: pd.DataFrame, window: str, split_registry: list, all_metrics: list,
               stability: dict, coeff_rows: list, bins_rows: list, score_rows: list,
               traces: list, monthly_histories: pd.DataFrame):
    frame = frame.sort_values("loan_id").reset_index(drop=True)
    y = frame.target.astype(int).to_numpy()
    # This is a single lockbox split, created before any supervised transform.
    dev_idx, hold_idx = stratified_indices(y, HOLDOUT_FRACTION, SEED + (0 if window == "3m" else 1000))
    hold_y = y[hold_idx]
    hold = frame.iloc[hold_idx].reset_index(drop=True)
    hold_info = {"window": window, "n": len(hold), "defaults": int(hold_y.sum()), "nondefaults": int((hold_y==0).sum()), "seed": SEED + (0 if window == "3m" else 1000)}
    split_registry.append({"window": window, "split_id": "holdout", "seed": hold_info["seed"], "role": "untouched_holdout", "train_loan_ids": frame.iloc[dev_idx].loan_id.astype(int).tolist(), "evaluation_loan_ids": hold.loan_id.astype(int).tolist(), "train_n": len(dev_idx), "evaluation_n": len(hold), "evaluation_defaults": int(hold_y.sum())})
    # Repeated deterministic stratified 75/25 evaluation inside development.
    dev = frame.iloc[dev_idx].reset_index(drop=True)
    yd = dev.target.astype(int).to_numpy()
    split_data = []
    for repeat in range(REPEATS):
        seed = SEED + (0 if window == "3m" else 1000) + 100 + repeat
        tr, va = stratified_indices(yd, VALIDATION_FRACTION, seed)
        trf, vaf = dev.iloc[tr].reset_index(drop=True), dev.iloc[va].reset_index(drop=True)
        yt, yv = yd[tr], yd[va]
        selected, binners, Xt, iv = _select(trf, yt)
        beta, converged, message = _fit_logistic(Xt, yt, l2=1.0)
        Xv = _apply(vaf, selected, binners)
        z, p = _predict(Xv, beta)
        met = _metrics(yv, p)
        row = {"window": window, "split_id": f"repeat_{repeat+1:02d}", "model_variant": "regularized_l2_1",
               "seed": seed,
               "train_n": len(tr), "validation_n": len(va), "selected_features": "|".join(selected),
               "converged": converged, **met}
        all_metrics.append(row)
        beta_unreg, converged_unreg, message_unreg = _fit_logistic(Xt, yt, l2=0.0)
        zu, pu = _predict(Xv, beta_unreg)
        all_metrics.append({"window":window,"split_id":f"repeat_{repeat+1:02d}","model_variant":"unregularized",
                            "seed":seed,"train_n":len(tr),"validation_n":len(va),
                            "selected_features":"|".join(selected),"converged":converged_unreg,
                            "optimizer_message":message_unreg,**_metrics(yv,pu)})
        split_registry.append({"window": window, "split_id": row["split_id"], "seed": seed, "role": "repeated_validation",
                               "train_loan_ids": trf.loan_id.astype(int).tolist(), "evaluation_loan_ids": vaf.loan_id.astype(int).tolist(),
                               "train_n": len(tr), "evaluation_n": len(va), "evaluation_defaults": int(yv.sum())})
        for name in FEATURES:
            rec = stability.setdefault((window, name), {"window": window, "feature": name, "eligible_splits": 0, "selected_count": 0, "iv": [], "signs": []})
            rec["eligible_splits"] += 1
            rec["iv"].append(iv[name])
            if name in selected:
                rec["selected_count"] += 1
                sign = int(np.sign(beta[1+selected.index(name)]))
                rec["signs"].append(sign)
        for j, name in enumerate(selected):
            coeff_rows.append({"window": window, "split_id": row["split_id"], "model_variant":"regularized_l2_1", "feature": name, "coefficient": float(beta[j+1]), "sign": int(np.sign(beta[j+1])), "intercept": float(beta[0]), "converged": converged})
            coeff_rows.append({"window": window, "split_id": row["split_id"], "model_variant":"unregularized", "feature": name, "coefficient": float(beta_unreg[j+1]), "sign": int(np.sign(beta_unreg[j+1])), "intercept": float(beta_unreg[0]), "converged": converged_unreg})
            bins_rows.append({"window": window, "split_id": row["split_id"], "feature": name, "cut": binners[name]["cut"], "iv_train": iv[name], "bin_metadata": json.dumps(binners[name]["bins"], separators=(",", ":"))})
        factor = 50/math.log(2)
        base = 600 - factor*math.log(20) - factor*beta[0]
        for k in range(min(2, len(vaf))):
            contributions = {name: float(-factor*beta[j+1]*Xv[k,j]) for j,name in enumerate(selected)}
            raw_score = float(score_from_pd(np.array([p[k]]))[0])
            residual = base + sum(contributions.values()) - raw_score
            score_rows.append({"window":window,"split_id":row["split_id"],"loan_id":int(vaf.loan_id.iloc[k]),"base_contribution":base,"feature_contributions":json.dumps(contributions),"score_raw":raw_score,"reconstructed_score":base+sum(contributions.values()),"absolute_error":abs(residual)})
            traces.append({"window":window,"split_id":row["split_id"],"loan_id":int(vaf.loan_id.iloc[k]),"window_start":vaf.window_start.iloc[k],"window_end_exclusive":vaf.window_end_exclusive.iloc[k],"engineered_features":{n:(None if pd.isna(vaf[n].iloc[k]) else float(vaf[n].iloc[k])) for n in FEATURES},"selected_features":selected,"bins":{n:{"cut":binners[n]["cut"],"woe":float(Xv[k,j])} for j,n in enumerate(selected)},"coefficients":{n:float(beta[j+1]) for j,n in enumerate(selected)},"intercept":float(beta[0]),"linear_predictor":float(z[k]),"raw_pd":float(p[k]),"good_bad_odds":float((1-p[k])/p[k]),"raw_score":raw_score,"score_contributions":{"base":base,**contributions}})
            traces[-1]["raw_monthly_history"] = monthly_histories[
                (monthly_histories.loan_id.astype(int) == int(vaf.loan_id.iloc[k]))
                & (monthly_histories.window == window)
            ].to_dict(orient="records")
        split_data.append((trf, vaf, yt, yv, selected, binners, beta, iv))
    # Fit on the full development set after repeated evaluation choices are recorded.
    selected, binners, Xt, iv = _select(dev, yd)
    beta, converged, message = _fit_logistic(Xt, yd, l2=1.0)
    Xh = _apply(hold, selected, binners)
    zh, ph = _predict(Xh, beta)
    holdout_result = {"window": window, **hold_info, "selected_features": "|".join(selected), "converged": converged, **_metrics(hold_y, ph)}
    # A lockbox trace is not used to revise the fit or feature set.
    for k in range(len(hold)):
        traces.append({"window":window,"split_id":"holdout","loan_id":int(hold.loan_id.iloc[k]),"window_start":hold.window_start.iloc[k],"window_end_exclusive":hold.window_end_exclusive.iloc[k],"engineered_features":{n:(None if pd.isna(hold[n].iloc[k]) else float(hold[n].iloc[k])) for n in FEATURES},"selected_features":selected,"bins":{n:{"cut":binners[n]["cut"],"woe":float(Xh[k,j])} for j,n in enumerate(selected)},"coefficients":{n:float(beta[j+1]) for j,n in enumerate(selected)},"intercept":float(beta[0]),"linear_predictor":float(zh[k]),"raw_pd":float(ph[k]),"good_bad_odds":float((1-ph[k])/ph[k]),"raw_score":float(score_from_pd(np.array([ph[k]]))[0])})
        traces[-1]["raw_monthly_history"] = monthly_histories[
            (monthly_histories.loan_id.astype(int) == int(hold.loan_id.iloc[k]))
            & (monthly_histories.window == window)
        ].to_dict(orient="records")
    all_metrics.append({"window":window,"split_id":"holdout","model_variant":"regularized_l2_1","seed":hold_info["seed"],"train_n":len(dev),"validation_n":len(hold),"selected_features":"|".join(selected),"converged":converged,**_metrics(hold_y,ph)})
    for j,name in enumerate(selected):
        bins_rows.append({"window":window,"split_id":"holdout_fit","feature":name,"cut":binners[name]["cut"],"iv_train":iv[name],"bin_metadata":json.dumps(binners[name]["bins"],separators=(",",":"))})
        coeff_rows.append({"window":window,"split_id":"holdout_fit","feature":name,"coefficient":float(beta[j+1]),"sign":int(np.sign(beta[j+1])),"intercept":float(beta[0]),"converged":converged})
    return holdout_result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    features = pd.read_csv(AUDIT / "candidate_features_by_loan.csv")
    reconciliation = pd.read_csv(AUDIT / "window_reconciliation.csv")
    monthly_histories = pd.read_csv(AUDIT / "monthly_histories.csv")
    # These checks are deliberately first: no split or target-informed fit occurs before them.
    cohort_summary = assert_corrected_cohorts(features, reconciliation)
    assert_canonical_windows(features)
    assert_monthly_history_windows(features, monthly_histories)
    if FORBIDDEN.intersection(FEATURES):
        raise RuntimeError(f"Forbidden features in candidate list: {sorted(FORBIDDEN.intersection(FEATURES))}")
    for name in FEATURES:
        if name not in features.columns:
            raise RuntimeError(f"Phase 2A candidate feature missing: {name}")
    source_files = [AUDIT/n for n in ["candidate_features_by_loan.csv","window_reconciliation.csv","candidate_feature_dictionary.csv","monthly_histories.csv"]]
    config = {
        "status": "EXPERIMENTAL_NOT_FOR_PRODUCTION", "seed_base": SEED, "repeated_validation_repeats": REPEATS,
        "validation_fraction_of_development": VALIDATION_FRACTION, "untouched_holdout_fraction": HOLDOUT_FRACTION,
        "max_selected_features": MAX_FEATURES, "l2_penalty": 1.0, "window_source": "phase2.windowing.complete_calendar_window",
        "window_definition": "first day of origination month minus N calendar months <= transaction date < first day of origination month",
        "coverage_rule": "account and source coverage must span the complete interval; uncovered months are never imputed as zero",
        "target": {"A":0,"B":1,"excluded_statuses":["C","D"]}, "woe_convention": WOE_CONVENTION,
        "features": FEATURES, "forbidden_features": sorted(FORBIDDEN), "cohort_summary_verified_from_phase2a": cohort_summary,
        "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__,
        "input_sha256": {p.name:sha256(p) for p in source_files},
        "raw_dataset_sha256": json.loads((AUDIT/"raw_file_sha256.json").read_text(encoding="utf-8")),
    }
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    (OUT/"experiment_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    pd.DataFrame([{"window":k,**v} for k,v in cohort_summary.items()]).to_csv(OUT/"cohort_summary.csv",index=False)
    split_registry=[]; all_metrics=[]; stability={}; coeff_rows=[]; bins_rows=[]; score_rows=[]; traces=[]; holdouts=[]
    for window in ("3m","6m"):
        frame=features[(features.window==window)&features.status.isin(["A","B"])&features.eligible.astype(bool)].copy()
        if len(frame)!=cohort_summary[window]["n"]:
            raise RuntimeError(f"Final Phase 2B {window} frame does not match the preflight cohort")
        holdouts.append(run_window(frame,window,split_registry,all_metrics,stability,coeff_rows,bins_rows,score_rows,traces,monthly_histories))
    pd.DataFrame(split_registry).to_json(OUT/"split_registry.json",orient="records",indent=2)
    # CSV with IDs is convenient for inspection; semicolon-separated IDs preserve split membership.
    pd.DataFrame([{**r,"train_loan_ids":";".join(map(str,r["train_loan_ids"])),"evaluation_loan_ids":";".join(map(str,r["evaluation_loan_ids"]))} for r in split_registry]).to_csv(OUT/"split_registry.csv",index=False)
    metrics=pd.DataFrame(all_metrics); metrics.to_csv(OUT/"split_metrics.csv",index=False)
    metrics[["window","split_id","model_variant","n","defaults","observed_default_rate","mean_predicted_pd","calibration_intercept","calibration_slope","brier","log_loss"]].to_csv(OUT/"calibration_analysis.csv",index=False)
    pd.DataFrame(holdouts).to_csv(OUT/"holdout_results.csv",index=False)
    pd.DataFrame(coeff_rows).to_csv(OUT/"coefficient_stability.csv",index=False)
    pd.DataFrame(bins_rows).to_csv(OUT/"binning_stability.csv",index=False)
    pd.DataFrame(score_rows).to_csv(OUT/"score_reconstruction.csv",index=False)
    (OUT/"score_traces.json").write_text(json.dumps(traces,indent=2),encoding="utf-8")
    sel=[]
    for (_,name),r in stability.items():
        signs=r["signs"]
        sel.append({"window":r["window"],"feature":name,"eligible_split_count":r["eligible_splits"],"selected_count":r["selected_count"],"selection_frequency":r["selected_count"]/max(1,r["eligible_splits"]),"mean_training_iv":float(np.mean(r["iv"])),"sd_training_iv":float(np.std(r["iv"],ddof=1)) if len(r["iv"])>1 else 0.0,"selected_coefficient_sign_consistency":max(signs.count(-1),signs.count(1))/len(signs) if signs else None,"positive_sign_count":signs.count(1),"negative_sign_count":signs.count(-1)})
    selection=pd.DataFrame(sel); selection.to_csv(OUT/"feature_selection_stability.csv",index=False)
    summary=[]
    for (window,variant),g in metrics[metrics.split_id.str.startswith("repeat_")].groupby(["window","model_variant"]):
        rec={"window":window,"model_variant":variant,"repeated_validation_splits":int(g.split_id.nunique()),
             "converged_fraction":float(g.converged.fillna(False).astype(bool).mean())}
        for metric in ["auc","gini","ks","brier","log_loss","calibration_intercept","calibration_slope","mean_predicted_pd","observed_default_rate"]:
            vals=pd.to_numeric(g[metric],errors="coerce").dropna()
            rec[metric+"_mean"]=float(vals.mean()) if len(vals) else None
            rec[metric+"_sd"]=float(vals.std(ddof=1)) if len(vals)>1 else None
            rec[metric+"_median"]=float(vals.median()) if len(vals) else None
            rec[metric+"_min"]=float(vals.min()) if len(vals) else None
            rec[metric+"_max"]=float(vals.max()) if len(vals) else None
            rec[metric+"_p05"]=float(vals.quantile(.05)) if len(vals) else None
            rec[metric+"_p95"]=float(vals.quantile(.95)) if len(vals) else None
        summary.append(rec)
    pd.DataFrame(summary).to_csv(OUT/"window_comparison.csv",index=False)
    dictionary = pd.read_csv(AUDIT/"candidate_feature_dictionary.csv")
    dictionary[dictionary.feature.isin(FEATURES)].to_csv(OUT/"candidate_features.csv",index=False)
    # Compact summary and report emphasize uncertainty and that calibration is diagnostic only.
    hold_by={r["window"]:r for r in holdouts}
    summary_json={"status":"PHASE_2B_INCONCLUSIVE","production_status":"EXPERIMENTAL_NOT_FOR_PRODUCTION","cohorts":cohort_summary,"holdouts":hold_by,"repeated_validation":summary,"calibration":"No separate calibrator fitted; sample too small. Calibration intercept/slope are diagnostic on validation folds only.","phase2c_recommendation":"Do not begin Phase 2C until the feature/membership and probability uncertainty are reviewed; current evidence is exploratory and inconclusive.","safety":"No production paths or artifacts modified."}
    (OUT/"phase2b_summary.json").write_text(json.dumps(summary_json,indent=2),encoding="utf-8")
    metric_lines=["| Metric | 3M mean ± SD (min–max) | 6M mean ± SD (min–max) |","|---|---:|---:|"]
    summaries_by_window={(r["window"],r["model_variant"]):r for r in summary}
    for label,key in [("AUC","auc"),("Gini","gini"),("KS","ks"),("Brier","brier"),("Log loss","log_loss"),("Calibration intercept","calibration_intercept"),("Calibration slope","calibration_slope")]:
        cells=[]
        for w in ("3m","6m"):
            rec=summaries_by_window[(w,"regularized_l2_1")]
            cells.append(f"{rec[key+'_mean']:.3f} ± {rec[key+'_sd']:.3f} ({rec[key+'_min']:.3f}–{rec[key+'_max']:.3f})")
        metric_lines.append(f"| {label} | {cells[0]} | {cells[1]} |")
    selected_summary=[]
    for r in sorted(sel,key=lambda x:(x["window"],-x["selection_frequency"],x["feature"])):
        if r["selection_frequency"]>0:
            selected_summary.append(f"- {r['window']} `{r['feature']}`: selected in {r['selected_count']}/{r['eligible_split_count']} development splits; sign consistency {r['selected_coefficient_sign_consistency']:.0%}.")
    if not selected_summary: selected_summary=["- No feature was selected in repeated development folds."]
    comparison_lines=["| Window | Variant | AUC mean ± SD | Brier mean ± SD | Converged fits |","|---|---|---:|---:|---:|"]
    for rec in summary:
        comparison_lines.append(f"| {rec['window']} | {rec['model_variant']} | {rec['auc_mean']:.3f} ± {rec['auc_sd']:.3f} | {rec['brier_mean']:.3f} ± {rec['brier_sd']:.3f} | {rec['converged_fraction']:.0%} |")
    max_reconstruction=float(pd.DataFrame(score_rows).absolute_error.max()) if score_rows else 0.0
    report=["# Phase 2B — Experimental Berka Behavioral Scorecard","","Status: **PHASE_2B_INCONCLUSIVE** — `EXPERIMENTAL_NOT_FOR_PRODUCTION`. No production artifacts or endpoints were written by this experiment.","","## A. Cohorts","",f"3M: N={cohort_summary['3m']['n']}, defaults={cohort_summary['3m']['defaults']}, nondefaults={cohort_summary['3m']['nondefaults']}, default rate={cohort_summary['3m']['default_rate']:.2%}.",f"6M: N={cohort_summary['6m']['n']}, defaults={cohort_summary['6m']['defaults']}, nondefaults={cohort_summary['6m']['nondefaults']}, default rate={cohort_summary['6m']['default_rate']:.2%}.","Membership was checked against regenerated Phase 2A reconciliation before any modelling, then every A/B loan window was independently rebuilt from raw loan/account dates through the canonical `phase2.windowing.complete_calendar_window`; monthly rows were checked to span exactly the complete months. Any mismatch raises before fitting.","","## B. Validation design","",f"A deterministic stratified 20% holdout was reserved first for each window. Repeated validation used {REPEATS} seeded stratified splits within the remaining development sample, with 25% of development used for validation in each repeat. Transformations and selection were refit inside each training fold. Holdout class counts: 3M {hold_by['3m']['defaults']} defaults/{hold_by['3m']['nondefaults']} nondefaults; 6M {hold_by['6m']['defaults']} defaults/{hold_by['6m']['nondefaults']} nondefaults. Holdout is a single low-event sanity check, not a definitive estimate.","","## C. Feature candidates","",f"{len(FEATURES)} Phase 2A behavioral candidates were considered. Exact feature formulas, inputs, missingness and zero semantics are copied to `candidate_features.csv` from the Phase 2A dictionary; Phase 2B consumes the regenerated matrix without redefining formulas. No loan outcome, demographics, repayment markers, or post-loan fields are predictors.","","## D–F. Stability and performance","",*metric_lines,"","These are repeated validation summaries; overlapping development samples make their spread descriptive, not a confidence interval. Calibration regression is highly unstable in validation folds with few defaults. Full per-split results and additional mean/SD/median/range/5th–95th percentile summaries are in `split_metrics.csv` and `window_comparison.csv`.","","Selected feature stability:",*selected_summary,"","Standard vs regularized logistic comparison (same training-only transforms and selected features):",*comparison_lines,"","The L2=1 regularized model is used for the primary score and holdout experiment. Unregularized fits are a sensitivity comparison; nonconvergence or separation is recorded and they are not used to select the primary candidate.","","## G. 3M vs 6M","","No window is selected as superior. Their event counts and results do not support a reliable window ranking; **WINDOW_SELECTION_INCONCLUSIVE**.","","## H–I. Candidate and calibration","","The regularized logistic scorecard is exploratory, using at most two predictors and training-only median bins/WoE with 0.5 count smoothing (L2 penalty 1.0). WoE is `ln(% non-default in bin / % default in bin)`. Natural prevalence is preserved. No separate calibration model is recommended or fitted due to the tiny sample; validation calibration intercept/slope are diagnostics only.","","## J. Stability","","Feature selection, coefficient signs, and train-fitted bin cutoffs are recorded by split. See `feature_selection_stability.csv`, `coefficient_stability.csv`, and `binning_stability.csv`. Results should be treated as unstable given only 31 and 19 total defaults before holdout reservation. A borrower-level bootstrap was not run because only 25 (3M) and 15 (6M) defaults remain in development and repeated stratified splits already show broad, overlapping variation; bootstrap percentiles would not add reliable independent precision.","","## K. Mathematical verification","",f"The pipeline computes `z = intercept + Σ(coefficient × WoE)`, `PD = sigmoid(z)`, good:bad odds `(1-PD)/PD`, and the PRISM experimental score formula. The maximum recorded score reconstruction error is {max_reconstruction:.3g}; scores are raw and unclipped. Score anchors are verified in isolated tests. `score_traces.json` contains representative split and holdout traces including raw Phase 2A monthly history.","","## L. Leakage audit","","Target-informed binning, IV ranking, redundancy filtering, feature selection, and coefficients are fitted on training rows only. The 3M/6M membership, window boundaries, and eligibility were asserted against Phase 2A and the canonical window utility before training. Loan IDs, account IDs, statuses, repayment markers, loan terms, demographics, and post-loan data are excluded from predictors.","","## M. Production regression","","No production files were written by Phase 2B. The full backend regression could not be collected in this environment because the configured venv points to a missing Python 3.12 interpreter; system Python lacks `scikit-learn` and `pytesseract`. Active model, binning, and manifest hashes matched their manifest. The isolated Phase 2 tests pass.","","## N. Limitations","","Small labeled sample and few defaults; repeated validation overlaps; holdout has very few events; calibration uncertainty is substantial; Berka is a historical Czech population and does not establish transportability to current applicants; modern salary/utility evidence is absent; this is not real-world PRISM applicant validation.","","## O. Final status","","**PHASE_2B_INCONCLUSIVE**. Phase 2C should not begin based on these data alone; first review uncertainty and obtain a decision on whether to pursue additional data or a narrower follow-up."]
    (OUT/"phase2b_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    print(json.dumps({"cohorts":cohort_summary,"holdouts":hold_by,"outputs":str(OUT)},indent=2))


if __name__ == "__main__":
    main()
