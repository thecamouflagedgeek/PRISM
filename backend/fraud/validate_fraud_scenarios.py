"""
PRISM — P1 Fraud Scenario Validation Suite

Purpose
-------
Validate the behaviour of the integrated fraud engine against six
representative synthetic borrower scenarios.

This is a validation suite, not a unit-test replacement.
It is intentionally separate from test_fraud.py so that rule-level
unit tests remain stable while scenario behaviour is evaluated.

Scenarios
---------
1. Clean borrower
2. Duplicate identity
3. Loan stacking / multiple recent applications
4. Transaction spike
5. Rapid money movement
6. Multiple simultaneous fraud signals

No production artifacts are modified.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Make the backend/fraud directory importable when this file is run directly.
# ---------------------------------------------------------------------------

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fraud_engine import FraudEngine


# ===========================================================================
# HELPERS
# ===========================================================================

def make_transaction(
    date: str,
    amount: float,
    transaction_type: str,
    closing_balance: float,
    narration: str = "",
) -> dict[str, Any]:
    """Create a canonical synthetic bank transaction."""

    return {
        "date": date,
        "amount": amount,
        "type": transaction_type,
        "closing_balance": closing_balance,
        "narration": narration,
    }


def make_borrower(
    application_id: str = "APP-001",
    pan: str = "ABCDE1234F",
    phone_number: str = "9876543210",
    bank_account: str = "1234567890",
    application_date: str = "2026-09-18T10:00:00",
    status: str = "PENDING",
) -> dict[str, Any]:
    """Create a synthetic borrower/application record."""

    return {
        "application_id": application_id,
        "pan": pan,
        "phone_number": phone_number,
        "bank_account": bank_account,
        "application_date": application_date,
        "status": status,
    }


def flag_names(result: dict[str, Any]) -> list[str]:
    """Return triggered rule names."""

    return [
        flag["rule"]
        for flag in result.get("flags", [])
    ]


def print_result(
    scenario_number: int,
    name: str,
    result: dict[str, Any],
    expected_rules: set[str],
    forbidden_rules: set[str] | None = None,
) -> bool:
    """Print and validate a scenario result."""

    forbidden_rules = forbidden_rules or set()

    actual_rules = set(flag_names(result))

    missing = expected_rules - actual_rules
    unexpected = actual_rules & forbidden_rules

    passed = not missing and not unexpected

    print()
    print("=" * 72)
    print(f"SCENARIO {scenario_number} — {name}")
    print("=" * 72)

    print(f"Fraud Score    : {result['fraud_score']} / 100")
    print(f"Fraud Status   : {result['fraud_status']}")
    print(f"Rules Triggered: {result['rule_count']}")
    print(f"Engine Version : {result['engine_version']}")

    if actual_rules:
        print("Triggered Rules:")
        for rule in sorted(actual_rules):
            print(f"  - {rule}")
    else:
        print("Triggered Rules:")
        print("  - NONE")

    if expected_rules:
        print("Expected Rules:")
        for rule in sorted(expected_rules):
            print(f"  - {rule}")
    else:
        print("Expected Rules:")
        print("  - NONE")

    if missing:
        print()
        print("MISSING EXPECTED RULES:")
        for rule in sorted(missing):
            print(f"  - {rule}")

    if unexpected:
        print()
        print("UNEXPECTED FORBIDDEN RULES:")
        for rule in sorted(unexpected):
            print(f"  - {rule}")

    print()
    print("Evidence:")

    for flag in result.get("flags", []):
        print(f"  [{flag['rule']}]")
        print(f"    severity : {flag.get('severity')}")
        print(f"    weight   : {flag.get('weight')}")
        print(f"    message  : {flag.get('message')}")
        print(f"    evidence : {flag.get('evidence')}")

    print()
    if passed:
        print("RESULT: PASS")
    else:
        print("RESULT: FAIL")

    return passed


# ===========================================================================
# SCENARIO 1 — CLEAN BORROWER
# ===========================================================================

def scenario_clean_borrower() -> tuple[dict[str, Any], set[str], set[str]]:
    borrower = make_borrower()

    transactions = [
        make_transaction(
            "2026-09-16",
            42000,
            "CREDIT",
            85000,
            "MONTHLY SALARY",
        ),
        make_transaction(
            "2026-09-17",
            8500,
            "DEBIT",
            76500,
            "RENT",
        ),
        make_transaction(
            "2026-09-18",
            2200,
            "DEBIT",
            74300,
            "UTILITY PAYMENT",
        ),
    ]

    result = FraudEngine().assess(
        borrower=borrower,
        applications=[borrower],
        transactions=transactions,
    )

    return result, set(), {
        "DUPLICATE_IDENTITY",
        "MULTIPLE_RECENT_APPLICATIONS",
        "ACTIVE_LOAN_OVERLAP",
        "RAPID_REAPPLICATION",
        "LARGE_DEPOSIT",
        "SUDDEN_BALANCE_INCREASE",
        "REPEATED_IDENTICAL_TRANSACTIONS",
        "CREDIT_DEBIT_SPIKE",
        "MONEY_IN_OUT_PATTERN",
        "ROUND_NUMBER_ACTIVITY",
        "ABNORMAL_BALANCE_BEHAVIOUR",
    }


# ===========================================================================
# SCENARIO 2 — DUPLICATE IDENTITY
# ===========================================================================

def scenario_duplicate_identity() -> tuple[dict[str, Any], set[str], set[str]]:
    borrower = make_borrower(
        application_id="APP-002",
        pan="ABCDE1234F",
        phone_number="9876543210",
        bank_account="1234567890",
    )

    previous_application = make_borrower(
        application_id="APP-OLD-002",
        pan="ABCDE1234F",
        phone_number="9123456780",
        bank_account="9988776655",
        application_date="2026-08-01T10:00:00",
        status="REJECTED",
    )

    transactions = [
        make_transaction(
            "2026-09-16",
            3000,
            "CREDIT",
            15000,
        ),
        make_transaction(
            "2026-09-17",
            1200,
            "DEBIT",
            13800,
        ),
    ]

    result = FraudEngine().assess(
        borrower=borrower,
        applications=[previous_application],
        transactions=transactions,
    )

    return result, {
        "DUPLICATE_IDENTITY",
    }, set()


# ===========================================================================
# SCENARIO 3 — LOAN STACKING / MULTIPLE RECENT APPLICATIONS
# ===========================================================================

def scenario_loan_stacking() -> tuple[dict[str, Any], set[str], set[str]]:
    borrower = make_borrower(
        application_id="APP-003",
        pan="FGHIJ5678K",
        phone_number="9000000001",
        bank_account="111122223333",
        application_date="2026-09-18T10:00:00",
    )

    recent_application_1 = make_borrower(
        application_id="APP-OLD-003-A",
        pan="FGHIJ5678K",
        phone_number="9000000001",
        bank_account="444455556666",
        application_date="2026-09-15T09:00:00",
        status="ACTIVE",
    )

    recent_application_2 = make_borrower(
        application_id="APP-OLD-003-B",
        pan="FGHIJ5678K",
        phone_number="9000000001",
        bank_account="777788889999",
        application_date="2026-09-12T09:00:00",
        status="ACTIVE",
    )

    transactions = [
        make_transaction(
            "2026-09-16",
            40000,
            "CREDIT",
            90000,
        ),
        make_transaction(
            "2026-09-17",
            7000,
            "DEBIT",
            83000,
        ),
    ]

    result = FraudEngine().assess(
        borrower=borrower,
        applications=[
            recent_application_1,
            recent_application_2,
        ],
        transactions=transactions,
    )

    return result, {
        "DUPLICATE_IDENTITY",
        "MULTIPLE_RECENT_APPLICATIONS",
        "RAPID_REAPPLICATION",
    }, set()


# ===========================================================================
# SCENARIO 4 — TRANSACTION SPIKE
# ===========================================================================

def scenario_transaction_spike() -> tuple[dict[str, Any], set[str], set[str]]:
    borrower = make_borrower(
        application_id="APP-004",
        pan="LMNOP1234Q",
        phone_number="9000000002",
        bank_account="222233334444",
    )

    transactions = [
        make_transaction(
            "2026-09-01",
            1100,
            "CREDIT",
            10000,
        ),
        make_transaction(
            "2026-09-02",
            1150,
            "CREDIT",
            11150,
        ),
        make_transaction(
            "2026-09-03",
            1050,
            "CREDIT",
            12200,
        ),
        make_transaction(
            "2026-09-04",
            5000,
            "CREDIT",
            17200,
        ),
    ]

    result = FraudEngine().assess(
        borrower=borrower,
        applications=[],
        transactions=transactions,
    )

    return result, {
        "LARGE_DEPOSIT",
        "CREDIT_DEBIT_SPIKE",
    }, set()


# ===========================================================================
# SCENARIO 5 — RAPID MONEY MOVEMENT
# ===========================================================================

def scenario_rapid_money_movement() -> tuple[dict[str, Any], set[str], set[str]]:
    borrower = make_borrower(
        application_id="APP-005",
        pan="RSTUV1234W",
        phone_number="9000000003",
        bank_account="333344445555",
    )

    transactions = [
        make_transaction(
            "2026-09-18T10:00:00",
            100000,
            "CREDIT",
            125000,
            "TRANSFER RECEIVED",
        ),
        make_transaction(
            "2026-09-18T18:00:00",
            85000,
            "DEBIT",
            40000,
            "TRANSFER OUT",
        ),
    ]

    result = FraudEngine().assess(
        borrower=borrower,
        applications=[],
        transactions=transactions,
    )

    return result, {
        "MONEY_IN_OUT_PATTERN",
    }, set()


# ===========================================================================
# SCENARIO 6 — MULTIPLE SIMULTANEOUS SIGNALS
# ===========================================================================

def scenario_multiple_signals() -> tuple[dict[str, Any], set[str], set[str]]:
    borrower = make_borrower(
        application_id="APP-006",
        pan="XYZAB9876C",
        phone_number="9000000004",
        bank_account="444455556666",
        application_date="2026-09-18T10:00:00",
    )

    previous_application = make_borrower(
        application_id="APP-OLD-006",
        pan="XYZAB9876C",
        phone_number="9000000004",
        bank_account="999900001111",
        application_date="2026-09-15T10:00:00",
        status="ACTIVE",
    )

    transactions = [
        # Normal credit baseline
        make_transaction(
            "2026-09-01",
            1000,
            "CREDIT",
            5000,
        ),
        make_transaction(
            "2026-09-02",
            1100,
            "CREDIT",
            6100,
        ),
        make_transaction(
            "2026-09-03",
            1050,
            "CREDIT",
            7150,
        ),

        # Normal debit baseline
        make_transaction(
            "2026-09-01",
            900,
            "DEBIT",
            4100,
        ),
        make_transaction(
            "2026-09-02",
            950,
            "DEBIT",
            5150,
        ),
        make_transaction(
            "2026-09-03",
            1000,
            "DEBIT",
            6150,
        ),

        # Suspicious large credit
        make_transaction(
            "2026-09-04T10:00:00",
            10000,
            "CREDIT",
            16150,
            "LARGE TRANSFER RECEIVED",
        ),

        # 85% leaves within 24 hours
        make_transaction(
            "2026-09-04T18:00:00",
            8500,
            "DEBIT",
            7650,
            "TRANSFER OUT",
        ),
    ]

    result = FraudEngine().assess(
        borrower=borrower,
        applications=[previous_application],
        transactions=transactions,
    )

    return result, {
        "DUPLICATE_IDENTITY",
        "RAPID_REAPPLICATION",
        "LARGE_DEPOSIT",
        "CREDIT_DEBIT_SPIKE",
        "MONEY_IN_OUT_PATTERN",
    }, set()

# ===========================================================================
# MAIN VALIDATION
# ===========================================================================

def main() -> int:
    print()
    print("=" * 72)
    print("PRISM — P1 FRAUD SCENARIO VALIDATION SUITE")
    print("=" * 72)
    print("Engine Version : P1-v1")
    print("Purpose        : Synthetic behavioural validation")
    print("Artifacts      : NONE MODIFIED")
    print()

    scenarios = [
        scenario_clean_borrower,
        scenario_duplicate_identity,
        scenario_loan_stacking,
        scenario_transaction_spike,
        scenario_rapid_money_movement,
        scenario_multiple_signals,
    ]

    scenario_names = [
        "Clean Borrower",
        "Duplicate Identity",
        "Loan Stacking / Recent Applications",
        "Transaction Spike",
        "Rapid Money Movement",
        "Multiple Simultaneous Signals",
    ]

    passed = 0
    failed = 0

    for index, (scenario, name) in enumerate(
        zip(scenarios, scenario_names),
        start=1,
    ):
        result, expected_rules, forbidden_rules = scenario()

        if print_result(
            scenario_number=index,
            name=name,
            result=result,
            expected_rules=expected_rules,
            forbidden_rules=forbidden_rules,
        ):
            passed += 1
        else:
            failed += 1

    print()
    print("=" * 72)
    print("FINAL SCENARIO VALIDATION SUMMARY")
    print("=" * 72)
    print(f"Scenarios Passed : {passed}")
    print(f"Scenarios Failed : {failed}")
    print(f"Total Scenarios  : {len(scenarios)}")

    if failed == 0:
        print()
        print("SCENARIO VALIDATION: PASSED")
        print("All six fraud scenarios behaved as expected.")
        return 0

    print()
    print("SCENARIO VALIDATION: FAILED")
    print("Review the individual scenario output above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())