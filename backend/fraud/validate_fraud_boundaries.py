"""
PRISM — P1 Fraud Boundary & False-Positive Validation Suite

Purpose
-------
Validate fraud-rule behaviour immediately below, at, and above configured
thresholds.

This suite does NOT modify:
    - fraud_rules.py
    - fraud_engine.py
    - production artifacts
    - rule weights
    - fraud thresholds

It is a read-only behavioural validation suite.

Boundary groups
----------------
1. LARGE_DEPOSIT
2. MONEY_IN_OUT_PATTERN
3. SUDDEN_BALANCE_INCREASE
4. RAPID_REAPPLICATION
5. CLEAN / near-threshold controls

The objective is to identify:
    - correct threshold behaviour
    - boundary-condition inconsistencies
    - unexpected flags / potential false positives
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


# ============================================================================
# IMPORT PATH
# ============================================================================

CURRENT_DIR = Path(__file__).resolve().parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fraud_engine import FraudEngine
from fraud_rules import (
    BALANCE_INCREASE_PERCENT,
    BALANCE_INCREASE_MULTIPLIER,
    LARGE_DEPOSIT_MULTIPLIER,
    MONEY_OUT_RATIO,
    MONEY_OUT_WINDOW_HOURS,
    RAPID_REAPPLICATION_DAYS,
)


# ============================================================================
# HELPERS
# ============================================================================

ENGINE = FraudEngine()


def borrower(
    application_id: str = "BOUNDARY-001",
    pan: str = "ABCDE1234F",
    phone: str = "9876543210",
    bank_account: str = "1234567890",
    application_date: str = "2026-09-18T10:00:00",
    status: str = "PENDING",
) -> dict[str, Any]:

    return {
        "application_id": application_id,
        "pan": pan,
        "phone_number": phone,
        "bank_account": bank_account,
        "application_date": application_date,
        "status": status,
    }


def tx(
    date: str,
    amount: float,
    transaction_type: str,
    closing_balance: float,
    narration: str = "",
) -> dict[str, Any]:

    return {
        "date": date,
        "amount": amount,
        "type": transaction_type,
        "closing_balance": closing_balance,
        "narration": narration,
    }


def rules(result: dict[str, Any]) -> set[str]:
    return {
        flag["rule"]
        for flag in result.get("flags", [])
    }


def run_engine(
    borrower_record: dict[str, Any],
    applications: list[dict[str, Any]] | None = None,
    transactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:

    return ENGINE.assess(
        borrower=borrower_record,
        applications=applications or [],
        transactions=transactions or [],
    )


def evaluate(
    number: int,
    name: str,
    result: dict[str, Any],
    expected: set[str],
    forbidden: set[str] | None = None,
) -> bool:

    forbidden = forbidden or set()

    actual = rules(result)

    missing = expected - actual
    unexpected = actual & forbidden

    passed = not missing and not unexpected

    print()
    print("=" * 78)
    print(f"CASE {number} — {name}")
    print("=" * 78)

    print(f"Fraud Score     : {result['fraud_score']} / 100")
    print(f"Fraud Status    : {result['fraud_status']}")
    print(f"Rules Triggered : {result['rule_count']}")

    print()
    print("Actual Rules:")
    if actual:
        for rule in sorted(actual):
            print(f"  - {rule}")
    else:
        print("  - NONE")

    print()
    print("Expected Rules:")
    if expected:
        for rule in sorted(expected):
            print(f"  - {rule}")
    else:
        print("  - NONE")

    if missing:
        print()
        print("MISSING:")
        for rule in sorted(missing):
            print(f"  - {rule}")

    if unexpected:
        print()
        print("UNEXPECTED:")
        for rule in sorted(unexpected):
            print(f"  - {rule}")

    print()
    print("RESULT:", "PASS" if passed else "FAIL")

    return passed


# ============================================================================
# 1. LARGE DEPOSIT
# ============================================================================

def _large_deposit_baseline() -> list[dict[str, Any]]:
    return [
        tx("2026-09-01", 1000, "CREDIT", 5000),
        tx("2026-09-02", 1000, "CREDIT", 6000),
        tx("2026-09-03", 1000, "CREDIT", 7000),
        tx("2026-09-04", 1000, "CREDIT", 8000),
        tx("2026-09-05", 1000, "CREDIT", 9000),
    ]


def case_large_deposit_below():
    """
    Candidate = 2.99x fixed historical median.
    Expected: LARGE_DEPOSIT does not trigger.
    """

    b = borrower(application_id="BOUNDARY-LD-BELOW")

    transactions = _large_deposit_baseline()

    transactions.append(
        tx(
            "2026-09-06",
            2990,
            "CREDIT",
            11990,
        )
    )

    result = run_engine(b, transactions=transactions)

    return result, set(), {"LARGE_DEPOSIT"}


def case_large_deposit_exact():
    """
    Candidate = exactly 3.0x fixed historical median.
    Expected: LARGE_DEPOSIT triggers.
    """

    b = borrower(application_id="BOUNDARY-LD-EXACT")

    transactions = _large_deposit_baseline()

    transactions.append(
        tx(
            "2026-09-06",
            3000,
            "CREDIT",
            12000,
        )
    )

    result = run_engine(b, transactions=transactions)

    return result, {"LARGE_DEPOSIT"}, set()


def case_large_deposit_above():
    """
    Candidate = 3.01x fixed historical median.
    Expected: LARGE_DEPOSIT triggers.
    """

    b = borrower(application_id="BOUNDARY-LD-ABOVE")

    transactions = _large_deposit_baseline()

    transactions.append(
        tx(
            "2026-09-06",
            3010,
            "CREDIT",
            12010,
        )
    )

    result = run_engine(b, transactions=transactions)

    return result, {"LARGE_DEPOSIT"}, set()


# ============================================================================
# 2. MONEY IN / OUT
# ============================================================================

def case_money_out_below():
    """
    79.9% leaves the account.

    Expected:
        MONEY_IN_OUT_PATTERN should NOT trigger.
    """

    b = borrower(application_id="BOUNDARY-MIO-BELOW")

    transactions = [
        tx(
            "2026-09-18T10:00:00",
            100000,
            "CREDIT",
            125000,
        ),
        tx(
            "2026-09-18T18:00:00",
            79900,
            "DEBIT",
            45100,
        ),
    ]

    result = run_engine(b, transactions=transactions)

    return result, set(), {"MONEY_IN_OUT_PATTERN"}


def case_money_out_exact():
    """
    Exactly 80% leaves within the configured time window.

    Expected:
        MONEY_IN_OUT_PATTERN SHOULD trigger because the rule uses
        a minimum ratio boundary.
    """

    b = borrower(application_id="BOUNDARY-MIO-EXACT")

    transactions = [
        tx(
            "2026-09-18T10:00:00",
            100000,
            "CREDIT",
            125000,
        ),
        tx(
            "2026-09-18T18:00:00",
            80000,
            "DEBIT",
            45000,
        ),
    ]

    result = run_engine(b, transactions=transactions)

    return result, {"MONEY_IN_OUT_PATTERN"}, set()


def case_money_out_above():
    """
    80.1% leaves the account.

    Expected:
        MONEY_IN_OUT_PATTERN triggers.
    """

    b = borrower(application_id="BOUNDARY-MIO-ABOVE")

    transactions = [
        tx(
            "2026-09-18T10:00:00",
            100000,
            "CREDIT",
            125000,
        ),
        tx(
            "2026-09-18T18:00:00",
            80100,
            "DEBIT",
            44900,
        ),
    ]

    result = run_engine(b, transactions=transactions)

    return result, {"MONEY_IN_OUT_PATTERN"}, set()


def case_money_out_exact_window():
    """
    Debit occurs exactly at 24 hours.

    The current implementation intentionally treats the window as strict:
        hours_after_credit < 24

    Therefore this MUST NOT trigger.
    """

    b = borrower(application_id="BOUNDARY-MIO-TIME")

    transactions = [
        tx(
            "2026-09-17T10:00:00",
            100000,
            "CREDIT",
            125000,
        ),
        tx(
            "2026-09-18T10:00:00",
            85000,
            "DEBIT",
            40000,
        ),
    ]

    result = run_engine(b, transactions=transactions)

    return result, set(), {"MONEY_IN_OUT_PATTERN"}


# ============================================================================
# 3. SUDDEN BALANCE INCREASE
# ============================================================================

def case_balance_below():
    """
    Balance increase = 99.9%.

    Expected:
        SUDDEN_BALANCE_INCREASE should NOT trigger.
    """

    b = borrower(application_id="BOUNDARY-BAL-BELOW")

    transactions = [
        tx(
            "2026-09-01",
            100,
            "CREDIT",
            10000,
        ),
        tx(
            "2026-09-02",
            9990,
            "CREDIT",
            19990,
        ),
    ]

    result = run_engine(b, transactions=transactions)

    return result, set(), {"SUDDEN_BALANCE_INCREASE"}


def case_balance_exact():
    """
    Balance doubles exactly.

    Increase = 100%.

    Expected:
        SUDDEN_BALANCE_INCREASE triggers because the configured
        minimum is 100%.
    """

    b = borrower(application_id="BOUNDARY-BAL-EXACT")

    transactions = [
        tx(
            "2026-09-01",
            100,
            "CREDIT",
            10000,
        ),
        tx(
            "2026-09-02",
            10000,
            "CREDIT",
            20000,
        ),
    ]

    result = run_engine(b, transactions=transactions)

    return result, {"SUDDEN_BALANCE_INCREASE"}, set()


def case_balance_above():
    """
    Balance increase > 100%.

    Expected:
        SUDDEN_BALANCE_INCREASE triggers.
    """

    b = borrower(application_id="BOUNDARY-BAL-ABOVE")

    transactions = [
        tx(
            "2026-09-01",
            100,
            "CREDIT",
            10000,
        ),
        tx(
            "2026-09-02",
            10100,
            "CREDIT",
            20100,
        ),
    ]

    result = run_engine(b, transactions=transactions)

    return result, {"SUDDEN_BALANCE_INCREASE"}, set()


# ============================================================================
# 4. RAPID REAPPLICATION
# ============================================================================

def case_reapplication_outside_window():
    """
    Matching application is exactly one hour outside the 7-day window.

    Current rule should NOT trigger RAPID_REAPPLICATION.
    """

    b = borrower(
        application_id="BOUNDARY-RA-OUTSIDE",
        application_date="2026-09-18T10:00:00",
    )

    old = borrower(
        application_id="BOUNDARY-RA-OLD",
        pan=b["pan"],
        phone=b["phone_number"],
        bank_account="9999999999",
        application_date="2026-09-11T09:00:00",
        status="REJECTED",
    )

    result = run_engine(
        b,
        applications=[old],
    )

    return result, set(), {"RAPID_REAPPLICATION"}


def case_reapplication_exact_window():
    """
    Matching application is exactly 7 days earlier.

    Expected:
        RAPID_REAPPLICATION triggers if the rule uses the inclusive
        configured boundary.
    """

    b = borrower(
        application_id="BOUNDARY-RA-EXACT",
        application_date="2026-09-18T10:00:00",
    )

    old = borrower(
        application_id="BOUNDARY-RA-OLD-EXACT",
        pan=b["pan"],
        phone=b["phone_number"],
        bank_account="9999999999",
        application_date="2026-09-11T10:00:00",
        status="REJECTED",
    )

    result = run_engine(
        b,
        applications=[old],
    )

    return result, {"RAPID_REAPPLICATION"}, set()


def case_reapplication_inside_window():
    """
    Matching application is 6 days 23 hours earlier.

    Expected:
        RAPID_REAPPLICATION triggers.
    """

    b = borrower(
        application_id="BOUNDARY-RA-INSIDE",
        application_date="2026-09-18T10:00:00",
    )

    old = borrower(
        application_id="BOUNDARY-RA-OLD-INSIDE",
        pan=b["pan"],
        phone=b["phone_number"],
        bank_account="9999999999",
        application_date="2026-09-11T11:00:00",
        status="REJECTED",
    )

    result = run_engine(
        b,
        applications=[old],
    )

    return result, {"RAPID_REAPPLICATION"}, set()


# ============================================================================
# 5. CLEAN CONTROL
# ============================================================================

def case_clean_near_threshold():
    """
    Combined normal activity designed to sit close to, but below,
    the principal transaction thresholds.

    Expected:
        No major transaction fraud flags.
    """

    b = borrower(
        application_id="BOUNDARY-CLEAN",
        application_date="2026-09-18T10:00:00",
    )

    transactions = [
        tx(
            "2026-09-15",
            1000,
            "CREDIT",
            10000,
        ),
        tx(
            "2026-09-16",
            1100,
            "CREDIT",
            11100,
        ),
        tx(
            "2026-09-17",
            1000,
            "CREDIT",
            12100,
        ),
        tx(
            "2026-09-17",
            900,
            "DEBIT",
            11200,
        ),
        tx(
            "2026-09-18",
            800,
            "DEBIT",
            10400,
        ),
    ]

    result = run_engine(
        b,
        applications=[],
        transactions=transactions,
    )

    return result, set(), {
        "LARGE_DEPOSIT",
        "MONEY_IN_OUT_PATTERN",
        "SUDDEN_BALANCE_INCREASE",
    }


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    print()
    print("=" * 78)
    print("PRISM — P1 FRAUD BOUNDARY & FALSE-POSITIVE VALIDATION")
    print("=" * 78)

    print()
    print("Configured Thresholds")
    print("-" * 78)
    print(f"LARGE_DEPOSIT_MULTIPLIER : {LARGE_DEPOSIT_MULTIPLIER}")
    print(f"MONEY_OUT_RATIO          : {MONEY_OUT_RATIO}")
    print(f"MONEY_OUT_WINDOW_HOURS   : {MONEY_OUT_WINDOW_HOURS}")
    print(f"BALANCE_INCREASE_PERCENT : {BALANCE_INCREASE_PERCENT}")
    print(f"BALANCE_INCREASE_MULTIPLIER: {BALANCE_INCREASE_MULTIPLIER}")
    print(f"RAPID_REAPPLICATION_DAYS : {RAPID_REAPPLICATION_DAYS}")

    cases = [
        (
            "Large deposit — below threshold",
            case_large_deposit_below,
        ),
        (
            "Large deposit — exact threshold",
            case_large_deposit_exact,
        ),
        (
            "Large deposit — above threshold",
            case_large_deposit_above,
        ),
        (
            "Money out — below 80%",
            case_money_out_below,
        ),
        (
            "Money out — exact 80%",
            case_money_out_exact,
        ),
        (
            "Money out — above 80%",
            case_money_out_above,
        ),
        (
            "Money out — exactly 24 hours",
            case_money_out_exact_window,
        ),
        (
            "Balance increase — below 100%",
            case_balance_below,
        ),
        (
            "Balance increase — exact 100%",
            case_balance_exact,
        ),
        (
            "Balance increase — above 100%",
            case_balance_above,
        ),
        (
            "Rapid reapplication — outside 7 days",
            case_reapplication_outside_window,
        ),
        (
            "Rapid reapplication — exact 7 days",
            case_reapplication_exact_window,
        ),
        (
            "Rapid reapplication — inside 7 days",
            case_reapplication_inside_window,
        ),
        (
            "Clean near-threshold control",
            case_clean_near_threshold,
        ),
    ]

    passed = 0
    failed = 0

    for number, (name, case) in enumerate(cases, start=1):

        result, expected, forbidden = case()

        if evaluate(
            number=number,
            name=name,
            result=result,
            expected=expected,
            forbidden=forbidden,
        ):
            passed += 1
        else:
            failed += 1

    print()
    print("=" * 78)
    print("FINAL BOUNDARY VALIDATION SUMMARY")
    print("=" * 78)

    print(f"Cases Passed : {passed}")
    print(f"Cases Failed : {failed}")
    print(f"Total Cases  : {len(cases)}")

    print()

    if failed == 0:
        print("BOUNDARY VALIDATION: PASSED")
        print("All configured threshold boundaries behaved as expected.")
        return 0

    print("BOUNDARY VALIDATION: FAILED")
    print("One or more threshold behaviours require review.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())