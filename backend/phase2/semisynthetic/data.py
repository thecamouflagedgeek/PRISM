"""Raw Berka loaders and corrected 3M real-parent construction."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from phase2.berka_audit import dte, load, num
from phase2.windowing import complete_calendar_window
from phase2.semisynthetic.feature_extraction import FEATURES, extract_behavioral_features

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "outputs" / "berka_audit"
DATA = ROOT / "berka"


def real_3m_parents():
    """Rebuild the complete 3M A/B cohort directly from raw loan/account dates."""
    account = num(load(DATA / "account.asc"))
    loan = num(load(DATA / "loan.asc"))
    trans = num(load(DATA / "trans.asc"))
    trans["source_order"] = np.arange(len(trans), dtype=int)
    account["parsed_date"] = dte(account.date)
    loan["parsed_date"] = dte(loan.date)
    trans["parsed_date"] = dte(trans.date)
    source_start = trans.parsed_date.min().date()
    source_end = (trans.parsed_date.max() + pd.Timedelta(days=1)).date()
    account_open = dict(zip(account.account_id.astype(int), account.parsed_date))
    account_map = dict(zip(loan.loan_id.astype(int), loan.account_id.astype(int)))
    loan_date = dict(zip(loan.loan_id.astype(int), loan.parsed_date))
    status = dict(zip(loan.loan_id.astype(int), loan.status.astype(str)))
    # Phase 2A candidate table used only as a frozen membership/feature reference.
    ref = pd.read_csv(AUDIT / "candidate_features_by_loan.csv")
    ref = ref[(ref.window == "3m") & ref.status.isin(["A", "B"]) & ref.eligible.astype(bool)].copy()
    if not ref.loan_id.is_unique:
        raise RuntimeError("Duplicate loan IDs in corrected Phase 2A 3M source")
    raw_ids = set()
    parent_rows = []
    for r in loan[loan.status.isin(["A", "B"])].itertuples(index=False):
        lid, aid = int(r.loan_id), int(r.account_id)
        cw = complete_calendar_window(
            pd.Timestamp(r.parsed_date).date(), 3,
            account_open_date=pd.Timestamp(account_open[aid]).date(),
            source_coverage_start=source_start,
            source_coverage_end_exclusive=source_end,
        )
        phase_rows = ref[ref.loan_id.astype(int) == lid]
        if cw.eligible:
            raw_ids.add(lid)
            if len(phase_rows) != 1:
                raise RuntimeError(f"Corrected Phase 2A lacks eligible raw 3M loan {lid}")
            if set(phase_rows.iloc[0][FEATURES].index) != set(FEATURES):
                raise RuntimeError("Candidate feature schema mismatch")
        elif len(phase_rows):
            raise RuntimeError(f"Phase 2A includes raw-ineligible 3M loan {lid}")
        if not cw.eligible:
            continue
        if str(phase_rows.iloc[0].window_start) != cw.window_start.isoformat() or str(phase_rows.iloc[0].window_end_exclusive) != cw.window_end_exclusive.isoformat():
            raise RuntimeError(f"Phase 2A window mismatch for loan {lid}")
        tx = trans[trans.account_id.astype(int) == aid].copy()
        # Match the exact order established by Phase 2A's txmap: sort by date
        # only, retaining pandas' deterministic tie handling for same-day rows.
        tx = tx.sort_values("parsed_date")
        tx = tx[(tx.parsed_date >= pd.Timestamp(cw.window_start)) & (tx.parsed_date < pd.Timestamp(cw.window_end_exclusive))]
        tx["date"] = tx.parsed_date
        if tx.empty:
            raise RuntimeError(f"Eligible raw 3M loan has empty history: {lid}")
        y = 1 if str(r.status) == "B" else 0
        features = extract_behavioral_features(
            tx, r.parsed_date, cw.window_start, cw.window_end_exclusive, months=3
        )
        reference = phase_rows.iloc[0]
        for feature in FEATURES:
            a, b = features[feature], reference[feature]
            if pd.isna(a) and pd.isna(b):
                continue
            if pd.isna(a) or pd.isna(b) or not np.isclose(float(a), float(b), atol=1e-7, rtol=1e-8):
                raise RuntimeError(f"Canonical extractor differs from Phase 2A for {lid}/{feature}: {a} != {b}")
        tx = tx[["trans_id","account_id","source_order","date","amount","type","k_symbol","balance"]].reset_index(drop=True)
        tx["date"] = pd.to_datetime(tx.date)
        parent_rows.append({
            "parent_loan_id": lid, "parent_account_id": aid, "status": str(r.status),
            "target": y, "label_source": "OBSERVED_BERKA", "is_synthetic": False,
            "loan_date": pd.Timestamp(r.parsed_date), "window_start": pd.Timestamp(cw.window_start),
            "window_end_exclusive": pd.Timestamp(cw.window_end_exclusive),
            "features": features, "transactions": tx,
        })
    if raw_ids != set(ref.loan_id.astype(int)):
        raise RuntimeError(f"Raw canonical 3M membership differs from Phase 2A: {sorted(raw_ids ^ set(ref.loan_id.astype(int)))}")
    summary = {
        "real_parent_n": len(parent_rows), "real_parent_defaults": sum(p["target"] for p in parent_rows),
        "real_parent_nondefaults": sum(1-p["target"] for p in parent_rows),
        "default_rate": float(np.mean([p["target"] for p in parent_rows])),
        "raw_membership_matches_corrected_phase2a": True,
        "old_window_archive_read": False,
        "feature_extractor_parity_all_features": True,
    }
    if (summary["real_parent_n"], summary["real_parent_defaults"], summary["real_parent_nondefaults"]) != (231,31,200):
        raise RuntimeError(f"Independent 3M raw cohort counts differ: {summary}")
    return parent_rows, summary
