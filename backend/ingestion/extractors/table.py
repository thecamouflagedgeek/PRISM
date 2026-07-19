"""
Table Extractor
----------------
Single responsibility: given normalized statement text, parse individual
transaction lines into structured rows. Contains the position-sensitive
amount parsing that must NOT sort by value — column meaning depends on
left-to-right order, not magnitude.
"""

import re
import pandas as pd
from typing import List, Optional, Tuple
from typing import List
import pandas as pd

DATE_PATTERNS = [
    re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4}\b"),
    re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2}\b"),
    re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*-\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b", re.IGNORECASE),
]

AMOUNT_PATTERN = re.compile(
    r"\b(?:\d{1,2},)?(?:\d{2},)*\d{3}(?:\.\d{1,2})?\b"
    r"|\b\d{1,6}\.\d{2}\b"
)

TRAILING_MARKER = re.compile(r"\b(CR|DR)\s*$")

# Standalone dash used as an "empty column" placeholder in tabular statements.
# Lookaround avoids matching a minus sign embedded inside a number.
DASH_TOKEN = re.compile(r"(?<!\d)-(?!\d)")


def find_date(text: str) -> Optional[str]:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group()
    return None


def find_all_amounts_ordered(text: str) -> List[float]:
    raw = AMOUNT_PATTERN.findall(text)

    print("\n--------------------------------------")
    print(text)
    print("Regex Matches :", raw)

    results = []
    for r in raw:
        try:
            results.append(float(r.replace(",", "")))
        except ValueError:
            pass

    print("Parsed Amounts:", results)
    return results

def clean_amount(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def detect_debit_credit_order(lines: List[str]) -> bool:
    """
    Returns True if the statement's header lists Debit before Credit,
    False if Credit comes first. Scans only the first 40 lines, where
    headers typically appear.
    """
    for line in lines[:40]:
        lower = line.lower()
        if "debit" in lower and "credit" in lower:
            return lower.index("debit") < lower.index("credit")
    return True  # default assumption if no header found


def parse_debit_credit_balance(
    line: str, debit_first: bool = True
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Assigns debit / credit / balance for a single transaction line using the
    sequence of numbers and standalone dashes (empty-column markers) — not
    character-offset column detection, which breaks on OCR/pdfplumber text
    that has no guaranteed fixed-width alignment between header and rows.
    """
    amounts = find_all_amounts_ordered(line)

    if len(amounts) == 0:
        return None, None, None

    debit, credit, balance = None, None, None

    if len(amounts) >= 3:
        if debit_first:
            debit, credit, balance = amounts[-3], amounts[-2], amounts[-1]
        else:
            credit, debit, balance = amounts[-3], amounts[-2], amounts[-1]

    elif len(amounts) == 2:
        balance = amounts[-1]

        # Which column is amounts[0] actually in? Compare the position of the
        # dash (empty-column placeholder) to the position of the FIRST amount
        # token in the raw line -- not just "is there a dash somewhere".
        dash_match = DASH_TOKEN.search(line)
        first_amount_match = re.search(r"[\d,]+\.\d{2}", line)

        if dash_match and first_amount_match:
            dash_before_first_amount = dash_match.start() < first_amount_match.start()
        else:
            # No dash found at all -- ambiguous, fall through to the
            # conservative default below.
            dash_before_first_amount = None

        if dash_before_first_amount is None:
            # No dash present: conservative fallback, assume first amount is
            # whichever column comes first per the statement's own header order.
            if debit_first:
                debit = amounts[0]
            else:
                credit = amounts[0]

        elif dash_before_first_amount:
            # Dash occupies the FIRST (leftmost) column -> that column is
            # empty, so amounts[0] belongs to the SECOND column.
            if debit_first:
                credit = amounts[0]   # debit column was the empty (dashed) one
            else:
                debit = amounts[0]    # credit column was the empty (dashed) one

        else:
            # Dash occupies the SECOND column -> amounts[0] belongs to the
            # FIRST column.
            if debit_first:
                debit = amounts[0]
            else:
                credit = amounts[0]

    elif len(amounts) == 1:
        balance = amounts[0]

    return debit, credit, balance

def parse_credit_card_transaction_line(line: str) -> dict | None:
    date = find_date(line)
    if not date:
        return None

    marker_match = TRAILING_MARKER.search(line.strip())
    if not marker_match:
        return None
    marker = marker_match.group(1)

    amounts = find_all_amounts_ordered(line)
    if not amounts:
        return None
    amount = amounts[-1]  # last amount before the CR/DR marker is the billed amount

    narration = line.replace(date, "").strip()
    narration = TRAILING_MARKER.sub("", narration).strip()
    narration = re.sub(r"[\d,]+\.\d{2}", "", narration).strip()

    return {"date": date, "narration": narration, "amount": amount, "type": marker}


def parse_credit_card_transactions(text: str) -> list[dict]:
    rows = []
    for line in text.split("\n"):
        row = parse_credit_card_transaction_line(line)
        if row:
            rows.append(row)
    return rows

def parse_transaction_rows(text: str) -> List[dict]:
    """
    Parses every date-anchored line in the statement text into a structured
    transaction row. Returns raw rows (unvalidated) — validation is a
    separate concern, handled by validators/consistency_validator.py.
    """
    lines = text.split("\n")
    debit_first = detect_debit_credit_order(lines)

    rows = []
    for line in lines:
        date = find_date(line)
        if not date:
            continue

        debit, credit, balance = parse_debit_credit_balance(line, debit_first=debit_first)
        if balance is None:
            continue

        narration = line.replace(date, "").strip()
        narration = re.sub(r"\b[\d,]+(?:\.\d{1,2})?\b", "", narration).strip()

        rows.append({
            "date": date,
            "narration": narration,
            "debit": debit,
            "credit": credit,
            "closing_balance": balance,
        })

    return rows


def build_transaction_df(rows: List[dict]) -> pd.DataFrame:
    """
    Converts parsed transaction rows into the canonical dataframe
    consumed by the feature engineering layer.
    """

    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "amount",
                "type",
                "narration",
                "closing_balance",
            ]
        )

    df = pd.DataFrame(rows)

    # Ensure all expected columns exist
    for col in ["date", "narration", "debit", "credit", "closing_balance"]:
        if col not in df.columns:
            df[col] = None

    # Clean numeric fields
    df["debit"] = df["debit"].apply(clean_amount)
    df["credit"] = df["credit"].apply(clean_amount)
    df["closing_balance"] = df["closing_balance"].apply(clean_amount)

    # Canonical amount column
    df["amount"] = df.apply(
        lambda r: (
            r["credit"]
            if pd.notna(r["credit"]) and r["credit"] > 0
            else (
                r["debit"]
                if pd.notna(r["debit"]) and r["debit"] > 0
                else None
            )
        ),
        axis=1,
    )

    # Transaction type
    def detect_type(row):
        if pd.notna(row["credit"]) and row["credit"] > 0:
            return "CR"
        elif pd.notna(row["debit"]) and row["debit"] > 0:
            return "DR"
        return None

    df["type"] = df.apply(detect_type, axis=1)

    # Keep only canonical columns
    final = df[
        [
            "date",
            "amount",
            "type",
            "narration",
            "closing_balance",
        ]
    ].copy()

    # Remove completely invalid rows
    final = final.dropna(subset=["date"]).reset_index(drop=True)

    return final