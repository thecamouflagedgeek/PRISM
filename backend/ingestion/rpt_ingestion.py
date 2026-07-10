"""
PRISM – .rpt File Ingestion Utility   (Part 9)
Handles bank statement exports in RPT (report/fixed-width/delimiter) format.
Assumptions are documented inline.
"""
from __future__ import annotations
import re
import io
from pathlib import Path
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np

# Assumption A1: RPT files may use fixed-width, pipe-delimited, or tab-delimited layout.
# Assumption A2: Header row exists (may be preceded by title/metadata lines).
# Assumption A3: Date fields follow DD-MM-YYYY or DD/MM/YYYY (Indian banking standard).
# Assumption A4: Amount fields use comma-thousand separators, e.g. "1,23,456.78".
# Assumption A5: Debit and credit may be in separate columns OR a single signed column.

_DATE_PATTERNS = [r"\d{2}[-/]\d{2}[-/]\d{4}", r"\d{4}[-/]\d{2}[-/]\d{2}"]
_AMOUNT_RE     = re.compile(r"^-?[\d,]+\.?\d*$")


def _clean_amount(val: str) -> Optional[float]:
    """Remove commas and parse Indian-format numbers."""
    if not isinstance(val, str):
        return None
    v = val.replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def _detect_delimiter(lines: List[str]) -> str:
    """Infer delimiter from the header/first data line."""
    candidates = ["|", "\t", ",", ";"]
    scores = {d: 0 for d in candidates}
    sample = lines[:min(5, len(lines))]
    for line in sample:
        for d in candidates:
            scores[d] += line.count(d)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None   # None → fixed-width


def _skip_metadata(lines: List[str]) -> int:
    """
    Skip banner/metadata lines until a header-like row is found.
    A header row has at least 3 non-numeric tokens separated by the delimiter.
    """
    for i, line in enumerate(lines):
        tokens = re.split(r"[|\t,;]", line)
        non_numeric = sum(1 for t in tokens if t.strip() and not _AMOUNT_RE.match(t.strip()))
        if non_numeric >= 3:
            return i
    return 0


def ingest_rpt(path: str) -> Tuple[pd.DataFrame, dict]:
    """
    Parse a .rpt bank statement into a clean DataFrame.
    Returns (df, metadata_dict) where metadata documents parsing assumptions used.
    """
    raw_path = Path(path)
    if not raw_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Read raw bytes; try UTF-8 then latin-1 (common in Indian bank exports)
    try:
        text = raw_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = raw_path.read_text(encoding="latin-1")

    lines = [l for l in text.splitlines() if l.strip()]
    meta  = {"source": str(path), "total_raw_lines": len(lines), "assumptions": []}

    # Detect delimiter
    delim = _detect_delimiter(lines)
    meta["delimiter"] = delim or "fixed-width"
    meta["assumptions"].append(f"A1: delimiter='{meta['delimiter']}'")

    # Skip metadata/banner rows
    header_idx = _skip_metadata(lines)
    meta["header_row"] = header_idx
    meta["assumptions"].append(f"A2: header at line {header_idx}")

    data_lines = lines[header_idx:]
    if not data_lines:
        raise ValueError("No parseable data found in .rpt file")

    if delim:
        df = pd.read_csv(io.StringIO("\n".join(data_lines)),
                         sep=re.escape(delim), engine="python",
                         on_bad_lines="warn")
    else:
        # Fixed-width fallback: infer column widths from header
        df = pd.read_fwf(io.StringIO("\n".join(data_lines)))

    # Normalise column names
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    # Detect and parse date column
    date_cols = [c for c in df.columns if any(k in c for k in ["date","dt","txn_date","tran"])]
    if date_cols:
        for dc in date_cols:
            try:
                df[dc] = pd.to_datetime(df[dc], dayfirst=True, errors="coerce")
            except Exception:
                pass
        meta["date_column"] = date_cols[0]
        meta["assumptions"].append("A3: dates parsed with dayfirst=True")

    # Detect and clean amount columns
    amount_cols = [c for c in df.columns if any(k in c for k in
                   ["amount","amt","debit","credit","dr","cr","balance","bal"])]
    for ac in amount_cols:
        df[ac] = df[ac].astype(str).apply(_clean_amount)
    meta["amount_columns"] = amount_cols
    meta["assumptions"].append("A4: amounts parsed after comma removal")

    # Infer signed transaction amount
    if "debit" in df.columns and "credit" in df.columns:
        df["transaction_amount"] = df["credit"].fillna(0) - df["debit"].fillna(0)
        meta["assumptions"].append("A5: transaction_amount = credit - debit")
    elif "amount" in df.columns:
        df["transaction_amount"] = df["amount"]

    meta["rows_parsed"]  = len(df)
    meta["columns"]      = list(df.columns)
    return df, meta


def engineer_features_from_rpt(df: pd.DataFrame) -> dict:
    """
    Compute PRISM bank features from a parsed RPT DataFrame.
    Returns a dict compatible with the bank_features argument of compute_risk_score().
    """
    out = {}
    if "transaction_amount" not in df.columns:
        return out

    credits = df[df["transaction_amount"] > 0]["transaction_amount"]
    debits  = df[df["transaction_amount"] < 0]["transaction_amount"].abs()

    total_credit = credits.sum()
    total_debit  = debits.sum()
    out["credit_debit_ratio"] = float(total_credit / total_debit) if total_debit > 0 else None

    # Monthly net cashflow CV
    if "date" in df.columns or any("date" in c for c in df.columns):
        date_col = next((c for c in df.columns if "date" in c), None)
        if date_col and pd.api.types.is_datetime64_any_dtype(df[date_col]):
            df = df.copy()
            df["_ym"] = df[date_col].dt.to_period("M")
            monthly = df.groupby("_ym")["transaction_amount"].sum()
            if len(monthly) > 1:
                out["cashflow_cv"] = float(monthly.std() / abs(monthly.mean())) if monthly.mean() != 0 else None

    # min_balance (last 3 months)
    bal_cols = [c for c in df.columns if "balance" in c or c == "bal"]
    if bal_cols:
        out["min_balance_l3m"] = float(df[bal_cols[0]].dropna().tail(90).min())

    return out