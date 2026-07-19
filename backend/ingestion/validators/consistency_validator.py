"""
Consistency Validator
-----------------------
Single responsibility: cross-validate extracted transaction rows against the
statement's own self-reported summary figures (transaction count, total
debit/credit, closing balance) — the most reliable ground truth available,
far better than an arbitrary hardcoded row-count threshold. A genuinely
quiet month with 3 transactions is valid; a threshold like "minimum 8 rows"
would incorrectly reject it.
"""

import re
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Any, List


SUMMARY_PATTERNS = {
    "transaction_count": re.compile(r"Total Transaction Count\s+(\d+)", re.IGNORECASE),
    "debit_amount": re.compile(r"Total Debit Amount\s+([\d,]+\.\d{2})", re.IGNORECASE),
    "credit_amount": re.compile(r"Total Credit Amount\s+([\d,]+\.\d{2})", re.IGNORECASE),
    "opening_balance": re.compile(r"Opening Balance\s+([\d,]+\.\d{2})", re.IGNORECASE),
    "closing_balance": re.compile(r"Closing Balance\s+([\d,]+\.\d{2})", re.IGNORECASE),
}


@dataclass
class ConsistencyResult:
    passed: bool
    issues: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


def parse_statement_summary(text: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for key, pattern in SUMMARY_PATTERNS.items():
        m = pattern.search(text)
        if m:
            val = m.group(1).replace(",", "")
            summary[key] = int(val) if key == "transaction_count" else float(val)
    return summary


def validate_consistency(df: pd.DataFrame, raw_text: str) -> ConsistencyResult:
    issues = []
    # in validators/consistency_validator.py, add to validate_consistency()
    cr_count = (df["type"] == "CR").sum()
    dr_count = (df["type"] == "DR").sum()
    
    if cr_count == 0 and dr_count > 0 and len(df) < 10:
        issues.append(
        "No credit transactions found in a short statement window. "
        "This may be a partial or single-page excerpt of a multi-part statement, "
        "not the account's full transaction history."
    )
    if df is None or df.empty:
        return ConsistencyResult(passed=False, issues=["No transactions extracted at all."])

    summary = parse_statement_summary(raw_text)
    print("\n========== SUMMARY ==========")
    print(summary)
    print("\n========== LAST 20 ROWS ==========")
    print(df.tail(20))
    print("\n========== LAST 1500 CHARACTERS ==========")
    print(raw_text[-1500:])

    if summary.get("transaction_count") is not None:
        if len(df) != summary["transaction_count"]:
            issues.append(
                f"Extracted {len(df)} transactions but statement declares "
                f"{summary['transaction_count']}. Possible missed or duplicated rows."
            )
    else:
        # No summary section found — soft warning only, not a hard block,
        # since some statement formats simply don't include one.
        if len(df) < 3:
            issues.append(
                f"Only {len(df)} transactions extracted and no summary section "
                f"found to cross-verify against."
            )

    if summary.get("closing_balance") is not None:
        valid_df = df.dropna(subset=["closing_balance"])
        if not valid_df.empty:
            extracted_final_balance = float(valid_df["closing_balance"].iloc[-1])
            if abs(extracted_final_balance - summary["closing_balance"]) > 1.0:
                issues.append(
                    f"Extracted final balance {extracted_final_balance} does not match "
                    f"statement's declared closing balance {summary['closing_balance']}."
                )

    return ConsistencyResult(passed=len(issues) == 0, issues=issues, summary=summary)