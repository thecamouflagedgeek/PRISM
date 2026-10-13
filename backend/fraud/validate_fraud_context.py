"""
PRISM — P1 FRAUD CONTEXT VALIDATION

Read-only contextual validation of existing fraud rules.

IMPORTANT:
- Does NOT modify fraud rules.
- Does NOT modify thresholds.
- Does NOT modify weights.
- Does NOT modify artifacts.
- Does NOT retrain anything.

Purpose:
    Distinguish:
        LEGITIMATE + rule triggered
            -> potential false positive

        SUSPICIOUS + rule triggered
            -> expected detection

        SUSPICIOUS + no rule triggered
            -> potential false negative

        LEGITIMATE + no rule triggered
            -> expected clean behaviour
"""

from datetime import datetime

from fraud_engine import FraudEngine


# ============================================================
# CONFIGURATION
# ============================================================

REFERENCE_TIME = datetime(2026, 9, 18, 12, 0, 0)


# ============================================================
# HELPERS
# ============================================================

def make_borrower(
    application_id="APP-001",
    pan="ABCDE1234F",
    phone_number="9876543210",
    bank_account="1234567890",
):
    return {
        "application_id": application_id,
        "pan": pan,
        "phone_number": phone_number,
        "bank_account": bank_account,
    }


def make_transaction(
    date,
    amount,
    tx_type,
    narration="",
    closing_balance=None,
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


# ============================================================
# SCENARIOS
# ============================================================

def build_scenarios():

    return [

        # ----------------------------------------------------
        # 1. NORMAL SALARY
        # ----------------------------------------------------

        {
            "name": "Salary only",
            "category": "SALARY",
            "expectation": "LEGITIMATE",
            "context": (
                "Single normal monthly salary credit."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
            ],
        },

        # ----------------------------------------------------
        # 2. RECURRING SALARY
        # ----------------------------------------------------

        {
            "name": "Recurring monthly salary",
            "category": "SALARY",
            "expectation": "LEGITIMATE",
            "context": (
                "Same employer salary received at regular "
                "monthly intervals."
            ),
            "transactions": [
                make_transaction(
                    "2026-07-01",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
                make_transaction(
                    "2026-08-01",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
                make_transaction(
                    "2026-09-01",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
            ],
        },

        # ----------------------------------------------------
        # 3. SALARY + NORMAL EXPENSES
        # ----------------------------------------------------

        {
            "name": "Salary plus normal expenses",
            "category": "SALARY_EXPENSES",
            "expectation": "LEGITIMATE",
            "context": (
                "Salary followed by ordinary rent, EMI and "
                "utility payments."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01T09:00:00",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
                make_transaction(
                    "2026-09-01T12:00:00",
                    15000,
                    "DR",
                    "RENT PAYMENT",
                ),
                make_transaction(
                    "2026-09-02",
                    8000,
                    "DR",
                    "EMI PAYMENT",
                ),
                make_transaction(
                    "2026-09-03",
                    2500,
                    "DR",
                    "ELECTRICITY BILL",
                ),
            ],
        },

        # ----------------------------------------------------
        # 4. SALARY + SUSPICIOUS RAPID TRANSFER
        # ----------------------------------------------------

        {
            "name": "Salary plus rapid unusual transfer",
            "category": "MONEY_MOVEMENT",
            "expectation": "SUSPICIOUS",
            "context": (
                "Normal salary followed by a large rapid "
                "transfer to an unexplained destination."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01T09:00:00",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
                make_transaction(
                    "2026-09-01T12:00:00",
                    45000,
                    "DR",
                    "TRANSFER",
                ),
            ],
        },

        # ----------------------------------------------------
        # 5. ONE-TIME UNEXPLAINED LARGE CREDIT
        # ----------------------------------------------------

        {
            "name": "One-time unexplained large credit",
            "category": "LARGE_TRANSFER",
            "expectation": "SUSPICIOUS",
            "context": (
                "Large one-time credit with no explanatory "
                "narration."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01",
                    100000,
                    "CR",
                    "",
                ),
            ],
        },

        # ----------------------------------------------------
        # 6. LARGE CREDIT EXPLICITLY IDENTIFIED AS SALARY
        # ----------------------------------------------------

        {
            "name": "Large credit with salary narration",
            "category": "LARGE_TRANSFER",
            "expectation": "LEGITIMATE",
            "context": (
                "Large credit explicitly identified as salary."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01",
                    100000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
            ],
        },

        # ----------------------------------------------------
        # 7. RECURRING LEGITIMATE LARGE TRANSFER
        # ----------------------------------------------------

        {
            "name": "Recurring legitimate large transfer",
            "category": "LARGE_TRANSFER",
            "expectation": "LEGITIMATE",
            "context": (
                "Large transfer occurring at regular monthly "
                "intervals with consistent narration."
            ),
            "transactions": [
                make_transaction(
                    "2026-07-01",
                    100000,
                    "CR",
                    "BUSINESS RECEIPT",
                ),
                make_transaction(
                    "2026-08-01",
                    100000,
                    "CR",
                    "BUSINESS RECEIPT",
                ),
                make_transaction(
                    "2026-09-01",
                    100000,
                    "CR",
                    "BUSINESS RECEIPT",
                ),
            ],
        },

        # ----------------------------------------------------
        # 8. SALARY → RENT
        # ----------------------------------------------------

        {
            "name": "Salary to rent",
            "category": "MONEY_MOVEMENT",
            "expectation": "LEGITIMATE",
            "context": (
                "Salary credit followed by rent payment "
                "on the same day."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01T09:00:00",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
                make_transaction(
                    "2026-09-01T18:00:00",
                    15000,
                    "DR",
                    "RENT PAYMENT",
                ),
            ],
        },

        # ----------------------------------------------------
        # 9. SALARY → EMI
        # ----------------------------------------------------

        {
            "name": "Salary to EMI",
            "category": "MONEY_MOVEMENT",
            "expectation": "LEGITIMATE",
            "context": (
                "Salary credit followed by scheduled EMI "
                "payment."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01T09:00:00",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
                make_transaction(
                    "2026-09-01T18:00:00",
                    8000,
                    "DR",
                    "EMI PAYMENT",
                ),
            ],
        },

        # ----------------------------------------------------
        # 10. SALARY → UTILITIES
        # ----------------------------------------------------

        {
            "name": "Salary to utilities",
            "category": "MONEY_MOVEMENT",
            "expectation": "LEGITIMATE",
            "context": (
                "Salary credit followed by normal electricity "
                "and utility payments."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01T09:00:00",
                    50000,
                    "CR",
                    "SALARY ABC COMPANY",
                ),
                make_transaction(
                    "2026-09-01T18:00:00",
                    2500,
                    "DR",
                    "ELECTRICITY BILL",
                ),
            ],
        },

        # ----------------------------------------------------
        # 11. UNEXPLAINED CREDIT → RAPID HIGH-VALUE DEBIT
        # ----------------------------------------------------

        {
            "name": "Unexplained credit to rapid debit",
            "category": "MONEY_MOVEMENT",
            "expectation": "SUSPICIOUS",
            "context": (
                "Large unexplained credit followed by a "
                "high-value debit within hours."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01T10:00:00",
                    100000,
                    "CR",
                    "",
                ),
                make_transaction(
                    "2026-09-01T14:00:00",
                    85000,
                    "DR",
                    "TRANSFER",
                ),
            ],
        },

        # ----------------------------------------------------
        # 12. REGULAR EMI RECURRENCE
        # ----------------------------------------------------

        {
            "name": "Regular EMI recurrence",
            "category": "REPEATED_TRANSACTIONS",
            "expectation": "LEGITIMATE",
            "context": (
                "Same EMI amount recurring across multiple "
                "months."
            ),
            "transactions": [
                make_transaction(
                    "2026-07-05",
                    8500,
                    "DR",
                    "EMI PAYMENT",
                ),
                make_transaction(
                    "2026-08-05",
                    8500,
                    "DR",
                    "EMI PAYMENT",
                ),
                make_transaction(
                    "2026-09-05",
                    8500,
                    "DR",
                    "EMI PAYMENT",
                ),
            ],
        },

        # ----------------------------------------------------
        # 13. RECURRING UTILITY
        # ----------------------------------------------------

        {
            "name": "Recurring utility payment",
            "category": "REPEATED_TRANSACTIONS",
            "expectation": "LEGITIMATE",
            "context": (
                "Repeated electricity bill payments with "
                "similar amounts."
            ),
            "transactions": [
                make_transaction(
                    "2026-07-10",
                    2200,
                    "DR",
                    "ELECTRICITY BILL",
                ),
                make_transaction(
                    "2026-08-10",
                    2200,
                    "DR",
                    "ELECTRICITY BILL",
                ),
                make_transaction(
                    "2026-09-10",
                    2200,
                    "DR",
                    "ELECTRICITY BILL",
                ),
            ],
        },

        # ----------------------------------------------------
        # 14. REPEATED MERCHANT PAYMENTS
        # ----------------------------------------------------

        {
            "name": "Repeated merchant payments",
            "category": "REPEATED_TRANSACTIONS",
            "expectation": "LEGITIMATE",
            "context": (
                "Repeated purchases from the same merchant "
                "with similar transaction amounts."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01",
                    2500,
                    "DR",
                    "GROCERY MART",
                ),
                make_transaction(
                    "2026-09-08",
                    2500,
                    "DR",
                    "GROCERY MART",
                ),
                make_transaction(
                    "2026-09-15",
                    2500,
                    "DR",
                    "GROCERY MART",
                ),
            ],
        },

        # ----------------------------------------------------
        # 15. REPEATED UNEXPLAINED HIGH-VALUE TRANSFERS
        # ----------------------------------------------------

        {
            "name": "Repeated unexplained transfers",
            "category": "REPEATED_TRANSACTIONS",
            "expectation": "SUSPICIOUS",
            "context": (
                "Repeated identical high-value transfers "
                "without legitimate narration."
            ),
            "transactions": [
                make_transaction(
                    "2026-09-01",
                    25000,
                    "DR",
                    "TRANSFER",
                ),
                make_transaction(
                    "2026-09-02",
                    25000,
                    "DR",
                    "TRANSFER",
                ),
                make_transaction(
                    "2026-09-03",
                    25000,
                    "DR",
                    "TRANSFER",
                ),
            ],
        },
    ]


# ============================================================
# CONTEXT ASSESSMENT
# ============================================================

def analyse_context(expectation, flags):

    triggered = len(flags) > 0

    if expectation == "LEGITIMATE":

        if triggered:
            return "POTENTIAL_FALSE_POSITIVE"

        return "EXPECTED_CLEAN"

    if expectation == "SUSPICIOUS":

        if triggered:
            return "EXPECTED_DETECTION"

        return "POTENTIAL_FALSE_NEGATIVE"

    return "UNCLASSIFIED"


# ============================================================
# MAIN VALIDATION
# ============================================================

def main():

    print("=" * 72)
    print("PRISM — P1 FRAUD CONTEXT VALIDATION")
    print("=" * 72)

    print()
    print("READ-ONLY VALIDATION")
    print(
        "No fraud rules, thresholds, weights, or artifacts "
        "will be modified."
    )
    print()

    engine = FraudEngine()
    borrower = make_borrower()

    scenarios = build_scenarios()

    summary = {
        "EXPECTED_CLEAN": 0,
        "EXPECTED_DETECTION": 0,
        "POTENTIAL_FALSE_POSITIVE": 0,
        "POTENTIAL_FALSE_NEGATIVE": 0,
    }

    for index, scenario in enumerate(
        scenarios,
        start=1,
    ):

        result = engine.assess(
    borrower,
    [borrower],
    scenario["transactions"],
)

        flags = result.get(
            "flags",
            [],
        )

        assessment = analyse_context(
            scenario["expectation"],
            flags,
        )

        summary[assessment] = (
            summary.get(assessment, 0) + 1
        )

        print("-" * 72)
        print(
            f"CASE {index} — "
            f"{scenario['name']}"
        )

        print(
            f"Expectation   : "
            f"{scenario['expectation']}"
        )

        print(
            f"Category      : "
            f"{scenario['category']}"
        )

        print(
            f"Context       : "
            f"{scenario['context']}"
        )

        print()

        print(
            f"Fraud Score   : "
            f"{result['fraud_score']} / 100"
        )

        print(
            f"Fraud Status  : "
            f"{result['fraud_status']}"
        )

        print("Rules:")

        if not flags:

            print("- NONE")

        else:

            for flag in flags:

                print(
                    f"- {flag['rule']} "
                    f"[{flag['category']}, "
                    f"{flag['severity']}, "
                    f"weight={flag['weight']}]"
                )

        print()
        print(
            f"Context Assessment: "
            f"{assessment}"
        )

        print()

    # ========================================================
    # SUMMARY
    # ========================================================

    print("=" * 72)
    print("CONTEXT VALIDATION SUMMARY")
    print("=" * 72)

    print(
        f"Total scenarios              : "
        f"{len(scenarios)}"
    )

    print(
        f"Expected clean               : "
        f"{summary['EXPECTED_CLEAN']}"
    )

    print(
        f"Expected detections          : "
        f"{summary['EXPECTED_DETECTION']}"
    )

    print(
        f"Potential false positives    : "
        f"{summary['POTENTIAL_FALSE_POSITIVE']}"
    )

    print(
        f"Potential false negatives    : "
        f"{summary['POTENTIAL_FALSE_NEGATIVE']}"
    )

    print()

    print("Interpretation:")

    print(
        "- EXPECTED_CLEAN means a legitimate scenario "
        "triggered no fraud rule."
    )

    print(
        "- EXPECTED_DETECTION means a suspicious scenario "
        "triggered at least one fraud rule."
    )

    print(
        "- POTENTIAL_FALSE_POSITIVE means a legitimate "
        "scenario triggered one or more rules."
    )

    print(
        "- POTENTIAL_FALSE_NEGATIVE means a suspicious "
        "scenario triggered no rules."
    )

    print()

    print(
        "This validation does not modify production "
        "fraud logic."
    )

    print()
    print(
        "CONTEXT VALIDATION COMPLETE"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()