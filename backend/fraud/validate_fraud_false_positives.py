"""
PRISM — P1 Fraud False-Positive Stress Validation

Purpose:
    Validate that realistic benign financial behaviour does not
    automatically produce strong fraud signals.

Important:
    This suite does NOT modify fraud rules or thresholds.
    It is an observational validation suite.

A benign scenario may legitimately trigger a weak heuristic
(e.g. round-number activity), but the result is recorded so
that potentially over-sensitive rules can be reviewed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fraud_engine import FraudEngine


REFERENCE_TIME = datetime(2026, 9, 18, 12, 0, 0)


# ============================================================
# TEST DATA HELPERS
# ============================================================

def borrower(application_id: str = "BENIGN-001") -> dict:
    return {
        "application_id": application_id,
        "pan": "ABCDE1234F",
        "phone_number": "9876543210",
        "bank_account": "1234567890",
        "application_date": REFERENCE_TIME.isoformat(),
        "status": "PENDING",
    }


def tx(
    date,
    amount,
    tx_type="CR",
    closing_balance=None,
    narration="",
):
    transaction = {
        "date": date,
        "amount": amount,
        "type": tx_type,
        "narration": narration,
    }

    if closing_balance is not None:
        transaction["closing_balance"] = closing_balance

    return transaction


def run_engine(
    b,
    transactions,
    applications=None,
):
    return FraudEngine().assess(
        borrower=b,
        applications=applications or [b],
        transactions=transactions,
        reference_time=REFERENCE_TIME,
    )


def rule_names(result):
    return {
        flag["rule"]
        for flag in result.get("flags", [])
    }


def print_result(name, result):
    print()
    print("=" * 78)
    print(name)
    print("=" * 78)

    print(f"Fraud Score     : {result['fraud_score']} / 100")
    print(f"Fraud Status    : {result['fraud_status']}")
    print(f"Rules Triggered : {result['rule_count']}")

    if result["flags"]:
        print()
        print("Actual Rules:")

        for flag in result["flags"]:
            print(
                f"  - {flag['rule']}"
                f" [{flag['category']}, {flag['severity']}]"
            )
    else:
        print()
        print("Actual Rules:")
        print("  - NONE")


# ============================================================
# SCENARIO 1
# NORMAL SALARY CREDIT
# ============================================================

def scenario_normal_salary_credit():
    """
    A monthly salary can be large relative to ordinary
    day-to-day transactions.

    It should not automatically be treated as fraud merely
    because it is a large credit.
    """

    b = borrower("BENIGN-SALARY")

    transactions = [
        tx(
            "2026-09-01",
            1200,
            "DR",
            13800,
            "GROCERIES",
        ),
        tx(
            "2026-09-03",
            950,
            "DR",
            12850,
            "UTILITY PAYMENT",
        ),
        tx(
            "2026-09-05",
            1500,
            "DR",
            11350,
            "HOUSEHOLD",
        ),
        tx(
            "2026-09-30",
            50000,
            "CR",
            61350,
            "SALARY CREDIT",
        ),
    ]

    return run_engine(b, transactions)


# ============================================================
# SCENARIO 2
# NORMAL RENT / FEE PAYMENT AFTER SALARY
# ============================================================

def scenario_normal_rent_payment():
    """
    Salary followed by a legitimate large rent payment.

    This intentionally resembles money-in/out behaviour,
    but the payment is a normal household obligation.
    """

    b = borrower("BENIGN-RENT")

    transactions = [
        tx(
            "2026-09-01T09:00:00",
            50000,
            "CR",
            65000,
            "SALARY CREDIT",
        ),
        tx(
            "2026-09-01T18:00:00",
            40000,
            "DR",
            25000,
            "MONTHLY HOUSE RENT",
        ),
        tx(
            "2026-09-05",
            2500,
            "DR",
            22500,
            "ELECTRICITY",
        ),
        tx(
            "2026-09-08",
            1800,
            "DR",
            20700,
            "GROCERIES",
        ),
    ]

    return run_engine(b, transactions)


# ============================================================
# SCENARIO 3
# LEGITIMATE REPEATED EMI
# ============================================================

def scenario_repeated_emi():
    """
    Identical EMI payments recurring monthly are legitimate
    repeated transactions.

    The rule may identify them because it intentionally looks
    for repeated identical amounts. That interaction is recorded
    rather than suppressing the rule.
    """

    b = borrower("BENIGN-EMI")

    transactions = [
        tx(
            "2026-07-05",
            12500,
            "DR",
            87500,
            "HOME LOAN EMI",
        ),
        tx(
            "2026-08-05",
            12500,
            "DR",
            75000,
            "HOME LOAN EMI",
        ),
        tx(
            "2026-09-05",
            12500,
            "DR",
            62500,
            "HOME LOAN EMI",
        ),
    ]

    return run_engine(b, transactions)


# ============================================================
# SCENARIO 4
# NORMAL MONTH-END BALANCE INCREASE
# ============================================================

def scenario_month_end_balance_increase():
    """
    Salary plus normal savings can produce a large balance
    increase at month-end.
    """

    b = borrower("BENIGN-SAVINGS")

    transactions = [
        tx(
            "2026-09-25",
            30000,
            "CR",
            35000,
            "SALARY",
        ),
        tx(
            "2026-09-27",
            5000,
            "DR",
            30000,
            "HOUSEHOLD EXPENSE",
        ),
        tx(
            "2026-09-30",
            25000,
            "CR",
            55000,
            "BONUS / SAVINGS TRANSFER",
        ),
    ]

    return run_engine(b, transactions)


# ============================================================
# SCENARIO 5
# LEGITIMATE MULTIPLE APPLICATIONS
# ============================================================

def scenario_legitimate_multiple_applications():
    """
    Multiple applications exist in the lender system, but they
    belong to different people and therefore should not produce
    identity or loan-stacking signals for the current borrower.
    """

    b = borrower("BENIGN-MULTI-APP")

    applications = [
        b,

        {
            "application_id": "OTHER-001",
            "pan": "ZZZZZ1111Z",
            "phone_number": "9000000001",
            "bank_account": "9000000001",
            "application_date": (
                REFERENCE_TIME - timedelta(days=2)
            ).isoformat(),
            "status": "PENDING",
        },

        {
            "application_id": "OTHER-002",
            "pan": "YYYYY2222Y",
            "phone_number": "9000000002",
            "bank_account": "9000000002",
            "application_date": (
                REFERENCE_TIME - timedelta(days=5)
            ).isoformat(),
            "status": "ACTIVE",
        },
    ]

    transactions = [
        tx(
            "2026-09-01",
            30000,
            "CR",
            40000,
            "SALARY",
        ),
        tx(
            "2026-09-03",
            5000,
            "DR",
            35000,
            "EXPENSE",
        ),
    ]

    return run_engine(
        b,
        transactions,
        applications,
    )


# ============================================================
# SCENARIO 6
# LEGITIMATE LARGE ONE-TIME TRANSFER
# ============================================================

def scenario_legitimate_large_transfer():
    """
    A large one-time transfer that is supported by a clear
    transaction narration and followed by ordinary activity.
    """

    b = borrower("BENIGN-LARGE-TRANSFER")

    transactions = [
        tx(
            "2026-09-01",
            25000,
            "CR",
            40000,
            "SALARY",
        ),
        tx(
            "2026-09-10",
            100000,
            "CR",
            140000,
            "PROPERTY SALE PROCEEDS",
        ),
        tx(
            "2026-09-12",
            4000,
            "DR",
            136000,
            "HOUSEHOLD",
        ),
        tx(
            "2026-09-15",
            3500,
            "DR",
            132500,
            "UTILITY",
        ),
    ]

    return run_engine(b, transactions)


# ============================================================
# SCENARIO 7
# NORMAL ROUND-NUMBER TRANSACTIONS
# ============================================================

def scenario_round_number_activity():
    """
    Round-number payments are common in rent, fees,
    tuition, transfers and business transactions.

    The rule may intentionally flag them; this scenario
    measures how that heuristic behaves in isolation.
    """

    b = borrower("BENIGN-ROUND")

    transactions = [
        tx(
            "2026-09-01",
            50000,
            "CR",
            70000,
            "SALARY",
        ),
        tx(
            "2026-09-02",
            20000,
            "DR",
            50000,
            "MONTHLY RENT",
        ),
        tx(
            "2026-09-05",
            10000,
            "DR",
            40000,
            "SCHOOL FEE",
        ),
        tx(
            "2026-09-10",
            15000,
            "DR",
            25000,
            "INSURANCE PREMIUM",
        ),
    ]

    return run_engine(b, transactions)


# ============================================================
# SCENARIO 8
# HIGH TRANSACTION VOLUME — NORMAL BEHAVIOUR
# ============================================================

def scenario_high_transaction_volume():
    """
    High transaction count alone should not imply fraud.

    Transactions remain within a relatively consistent range
    and no identity anomalies are introduced.
    """

    b = borrower("BENIGN-HIGH-VOLUME")

    transactions = []

    balance = 50000

    for day in range(1, 16):
        credit = 5000 + (day % 3) * 250

        transactions.append(
            tx(
                f"2026-09-{day:02d}",
                credit,
                "CR",
                balance + credit,
                "REGULAR INCOME",
            )
        )

        balance += credit

        debit_1 = 1800 + (day % 4) * 100
        transactions.append(
            tx(
                f"2026-09-{day:02d}T12:00:00",
                debit_1,
                "DR",
                balance - debit_1,
                "DAILY EXPENSE",
            )
        )

        balance -= debit_1

        debit_2 = 1200 + (day % 3) * 100
        transactions.append(
            tx(
                f"2026-09-{day:02d}T18:00:00",
                debit_2,
                "DR",
                balance - debit_2,
                "CARD PAYMENT",
            )
        )

        balance -= debit_2

    return run_engine(b, transactions)


# ============================================================
# VALIDATION
# ============================================================

SCENARIOS = [
    (
        "CASE 1 — Normal salary credit",
        scenario_normal_salary_credit,
    ),
    (
        "CASE 2 — Normal rent / fee payment after salary",
        scenario_normal_rent_payment,
    ),
    (
        "CASE 3 — Legitimate repeated EMI transactions",
        scenario_repeated_emi,
    ),
    (
        "CASE 4 — Normal month-end balance increase",
        scenario_month_end_balance_increase,
    ),
    (
        "CASE 5 — Legitimate multiple applications",
        scenario_legitimate_multiple_applications,
    ),
    (
        "CASE 6 — Legitimate large one-time transfer",
        scenario_legitimate_large_transfer,
    ),
    (
        "CASE 7 — Normal round-number transactions",
        scenario_round_number_activity,
    ),
    (
        "CASE 8 — High transaction-volume normal account",
        scenario_high_transaction_volume,
    ),
]


def main():
    print("=" * 78)
    print("PRISM — P1 FRAUD FALSE-POSITIVE STRESS VALIDATION")
    print("=" * 78)

    print()
    print("Purpose")
    print("-" * 78)
    print(
        "Evaluate realistic benign financial behaviour that may "
        "resemble fraud signals."
    )
    print(
        "This suite is observational and does not modify "
        "fraud rules or thresholds."
    )

    results = []

    for name, scenario in SCENARIOS:
        result = scenario()
        print_result(name, result)

        results.append(
            {
                "name": name,
                "score": result["fraud_score"],
                "status": result["fraud_status"],
                "rules": rule_names(result),
            }
        )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 78)
    print("FALSE-POSITIVE STRESS SUMMARY")
    print("=" * 78)

    for item in results:
        rules = (
            ", ".join(sorted(item["rules"]))
            if item["rules"]
            else "NONE"
        )

        print(
            f"{item['name']:<52}"
            f" Score={item['score']:>3}"
            f"  Status={item['status']:<8}"
            f" Rules={rules}"
        )

    print()
    print("=" * 78)
    print("INTERPRETATION")
    print("=" * 78)

    print(
        """
This suite does not automatically classify every non-zero
score as a production false positive.

A rule triggering on a benign scenario indicates a heuristic
interaction that should be reviewed.

Particular attention should be given to:
  - strong fraud statuses on benign scenarios
  - multiple simultaneous rules
  - identity rules triggered despite different identities
  - transaction rules triggered by clearly routine behaviour
  - repeated or round-number rules producing persistent signals

No fraud thresholds or production rules were modified.
"""
    )


if __name__ == "__main__":
    main()