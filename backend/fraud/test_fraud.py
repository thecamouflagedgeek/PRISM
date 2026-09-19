from datetime import datetime, timedelta

from fraud_engine import FraudEngine

from fraud_rules import (
    abnormal_balance_behaviour,
    active_loan_overlap,
    credit_debit_spike,
    duplicate_identity,
    large_deposit,
    money_in_out_pattern,
    multiple_recent_applications,
    rapid_reapplication,
    repeated_identical_transactions,
    round_number_activity,
    sudden_balance_increase,
)


REFERENCE_TIME = datetime(
    2026,
    9,
    18,
    12,
    0,
    0,
)


# ============================================================
# TEST DATA HELPERS
# ============================================================

def make_application(
    application_id,
    **kwargs
):

    application = {
        "application_id":
            application_id,

        "pan":
            "ABCDE1234F",

        "phone_number":
            "9876543210",

        "bank_account":
            "1234567890",

        "application_date":
            REFERENCE_TIME.isoformat(),

        "status":
            "PENDING",
    }

    application.update(kwargs)

    return application


def make_transaction(
    date,
    amount=None,
    tx_type="CR",
    closing_balance=None,
    narration="",
):

    transaction = {
        "date": date,
        "type": tx_type,
        "narration": narration,
    }

    if amount is not None:
        transaction["amount"] = amount

    if closing_balance is not None:
        transaction["closing_balance"] = (
            closing_balance
        )

    return transaction


# ============================================================
# IDENTITY RULES
# ============================================================

def test_duplicate_identity():

    borrower = make_application("A0")

    matching_application = make_application(
        "A1"
    )

    result = duplicate_identity(
        borrower,
        [
            borrower,
            matching_application,
        ],
    )

    assert result is not None
    assert result["rule"] == "DUPLICATE_IDENTITY"


def test_duplicate_identity_clean_case():

    borrower = make_application("A0")

    different_application = make_application(
        "A1",
        pan="ZZZZZ9999Z",
        phone_number="9000000000",
        bank_account="9999999999",
    )

    result = duplicate_identity(
        borrower,
        [
            borrower,
            different_application,
        ],
    )

    assert result is None


def test_multiple_recent_applications():

    borrower = make_application("A0")

    application_1 = make_application(
        "A1",
        application_date=(
            REFERENCE_TIME
            - timedelta(days=2)
        ).isoformat(),
    )

    application_2 = make_application(
        "A2",
        application_date=(
            REFERENCE_TIME
            - timedelta(days=10)
        ).isoformat(),
    )

    result = multiple_recent_applications(
        borrower,
        [
            borrower,
            application_1,
            application_2,
        ],
        REFERENCE_TIME,
    )

    assert result is not None
    assert (
        result["rule"]
        == "MULTIPLE_RECENT_APPLICATIONS"
    )


def test_active_loan_overlap():

    borrower = make_application("A0")

    application_1 = make_application(
        "A1",
        status="ACTIVE",
    )

    application_2 = make_application(
        "A2",
        status="DISBURSED",
    )

    result = active_loan_overlap(
        borrower,
        [
            borrower,
            application_1,
            application_2,
        ],
    )

    assert result is not None
    assert (
        result["rule"]
        == "ACTIVE_LOAN_OVERLAP"
    )


def test_rapid_reapplication():

    borrower = make_application("A0")

    application_1 = make_application(
        "A1",
        application_date=(
            REFERENCE_TIME
            - timedelta(days=3)
        ).isoformat(),
    )

    result = rapid_reapplication(
        borrower,
        [
            borrower,
            application_1,
        ],
        REFERENCE_TIME,
    )

    assert result is not None
    assert (
        result["rule"]
        == "RAPID_REAPPLICATION"
    )


# ============================================================
# TRANSACTION RULES
# ============================================================

def test_large_deposit():

    transactions = [
        make_transaction(
            "2026-09-01",
            1000,
            "CR",
        ),
        make_transaction(
            "2026-09-02",
            1200,
            "CR",
        ),
        make_transaction(
            "2026-09-03",
            1100,
            "CR",
        ),
        make_transaction(
            "2026-09-04",
            5000,
            "CR",
        ),
    ]

    result = large_deposit(
        transactions
    )

    assert result is not None
    assert result["rule"] == "LARGE_DEPOSIT"


def test_sudden_balance_increase():

    transactions = [
        make_transaction(
            "2026-09-01",
            1000,
            "CR",
            closing_balance=5000,
        ),
        make_transaction(
            "2026-09-02",
            1000,
            "CR",
            closing_balance=12000,
        ),
    ]

    result = sudden_balance_increase(
        transactions
    )

    assert result is not None
    assert (
        result["rule"]
        == "SUDDEN_BALANCE_INCREASE"
    )


def test_repeated_identical_transactions():

    transactions = [
        make_transaction(
            "2026-09-01",
            25000,
            "CR",
            narration="SALARY",
        ),
        make_transaction(
            "2026-09-02",
            25000,
            "CR",
            narration="SALARY",
        ),
        make_transaction(
            "2026-09-03",
            25000,
            "CR",
            narration="SALARY",
        ),
    ]

    result = repeated_identical_transactions(
        transactions
    )

    assert result is not None
    assert (
        result["rule"]
        == "REPEATED_IDENTICAL_TRANSACTIONS"
    )


def test_credit_debit_spike():

    transactions = [
        make_transaction(
            f"2026-09-{i:02d}",
            1000 + i * 10,
            "CR",
        )
        for i in range(1, 8)
    ]

    transactions.append(
        make_transaction(
            "2026-09-20",
            100000,
            "DR",
        )
    )

    result = credit_debit_spike(
        transactions
    )

    assert result is not None
    assert (
        result["rule"]
        == "CREDIT_DEBIT_SPIKE"
    )


def test_money_in_out_pattern():

    transactions = [
        make_transaction(
            "2026-09-01T10:00:00",
            100000,
            "CR",
        ),
        make_transaction(
            "2026-09-01T18:00:00",
            85000,
            "DR",
        ),
    ]

    result = money_in_out_pattern(
        transactions
    )

    assert result is not None
    assert (
        result["rule"]
        == "MONEY_IN_OUT_PATTERN"
    )


def test_round_number_activity():

    transactions = [
        make_transaction(
            "2026-09-01",
            10000,
            "CR",
        ),
        make_transaction(
            "2026-09-02",
            20000,
            "DR",
        ),
    ]

    result = round_number_activity(
        transactions
    )

    assert result is not None
    assert (
        result["rule"]
        == "ROUND_NUMBER_ACTIVITY"
    )


def test_abnormal_balance_behaviour():

    transactions = [
        make_transaction(
            "2026-09-01",
            1000,
            "DR",
            closing_balance=500,
        ),
        make_transaction(
            "2026-09-02",
            1000,
            "DR",
            closing_balance=800,
        ),
        make_transaction(
            "2026-09-03",
            1000,
            "DR",
            closing_balance=-200,
        ),
    ]

    result = abnormal_balance_behaviour(
        transactions
    )

    assert result is not None
    assert (
        result["rule"]
        == "ABNORMAL_BALANCE_BEHAVIOUR"
    )


# ============================================================
# ENGINE TESTS
# ============================================================

def test_engine_clean_case():

    borrower = {
        "application_id":
            "A0",

        "pan":
            "ABCDE1234F",

        "phone_number":
            "9876543210",

        "bank_account":
            "1234567890",
    }

    transactions = [
        make_transaction(
            "2026-09-01",
            1000,
            "CR",
            closing_balance=5000,
        ),
        make_transaction(
            "2026-09-02",
            900,
            "DR",
            closing_balance=4100,
        ),
    ]

    result = FraudEngine().assess(
        borrower,
        [borrower],
        transactions,
    )

    assert result["fraud_score"] == 0
    assert result["fraud_status"] == "CLEAR"
    assert result["flags"] == []


def test_engine_collects_multiple_flags():

    borrower = make_application("A0")

    applications = [
        borrower,

        make_application(
            "A1",
            application_date=(
                REFERENCE_TIME
                - timedelta(days=2)
            ).isoformat(),
            status="ACTIVE",
        ),

        make_application(
            "A2",
            application_date=(
                REFERENCE_TIME
                - timedelta(days=5)
            ).isoformat(),
            status="ACTIVE",
        ),
    ]

    transactions = [
        make_transaction(
            "2026-09-01",
            1000,
            "CR",
        ),
        make_transaction(
            "2026-09-02",
            1100,
            "CR",
        ),
        make_transaction(
            "2026-09-03",
            1000,
            "CR",
        ),
        make_transaction(
            "2026-09-04",
            5000,
            "CR",
        ),
        make_transaction(
            "2026-09-05",
            10000,
            "DR",
        ),
        make_transaction(
            "2026-09-06",
            10000,
            "DR",
        ),
    ]

    result = FraudEngine().assess(
        borrower,
        applications,
        transactions,
        REFERENCE_TIME,
    )

    assert result["fraud_score"] <= 100
    assert result["rule_count"] >= 3

    for flag in result["flags"]:
        assert "rule" in flag
        assert "weight" in flag
        assert "message" in flag
        assert "evidence" in flag

    assert (
        "not a calibrated probability"
        in result["score_semantics"]
    )