"""
PRISM P1 — Fraud Detection Rules

Contains deterministic, explainable identity/loan-stacking and
transaction-anomaly rules.

Important:
    fraud_score is NOT a probability.
    These are engineering rules and thresholds that must be validated
    against suitable fraud-labelled data before production use.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import math
import re
from statistics import mean, median, pstdev
from typing import Any, Mapping, Sequence


# ============================================================
# RULE WEIGHTS
# ============================================================

RULE_WEIGHTS = {
    "DUPLICATE_IDENTITY": 30,
    "MULTIPLE_RECENT_APPLICATIONS": 25,
    "ACTIVE_LOAN_OVERLAP": 30,
    "RAPID_REAPPLICATION": 20,

    "LARGE_DEPOSIT": 20,
    "SUDDEN_BALANCE_INCREASE": 25,
    "REPEATED_IDENTICAL_TRANSACTIONS": 15,
    "CREDIT_DEBIT_SPIKE": 20,
    "MONEY_IN_OUT_PATTERN": 25,
    "ROUND_NUMBER_ACTIVITY": 10,
    "ABNORMAL_BALANCE_BEHAVIOUR": 20,
}


# ============================================================
# THRESHOLDS
# ============================================================

RECENT_APPLICATION_DAYS = 30
RAPID_REAPPLICATION_DAYS = 7

LARGE_DEPOSIT_MULTIPLIER = 3.0

BALANCE_INCREASE_MULTIPLIER = 2.0
BALANCE_INCREASE_PERCENT = 100.0

SPIKE_ZSCORE = 3.0

REPEATED_TRANSACTION_COUNT = 3

MONEY_OUT_WINDOW_HOURS = 24
MONEY_OUT_RATIO = 0.80

ROUND_NUMBER_MIN = 10_000.0

NEAR_ZERO_BALANCE = 1_000.0


IDENTITY_FIELDS = (
    "pan",
    "phone_number",
    "bank_account",
    "borrower_id",
)

ACTIVE_STATUSES = {
    "ACTIVE",
    "APPROVED",
    "DISBURSED",
    "IN_PROGRESS",
    "PENDING",
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def normalize_identifier(value: Any) -> str:
    """
    Normalize an identifier before comparison.

    Example:
        'abcde-1234-f' -> 'ABCDE1234F'
    """
    if value is None:
        return ""

    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper()
    )


def hash_identifier(value: Any) -> str:
    """
    SHA-256 hash of normalized identifier.

    Raw identifier is never returned by this function.
    """
    normalized = normalize_identifier(value)

    if not normalized:
        return ""

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def parse_datetime(value: Any) -> datetime | None:
    """Parse common ISO/date formats."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    formats = (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def numeric(
    value: Any,
    default: float | None = None
) -> float | None:
    """Safely convert financial values to float."""
    try:
        if value is None:
            return default

        text = str(value).strip()

        if not text:
            return default

        text = (
            text
            .replace(",", "")
            .replace("₹", "")
            .strip()
        )

        return float(text)

    except (TypeError, ValueError):
        return default


def transaction_amount(
    transaction: Mapping[str, Any]
) -> float:
    """
    Extract transaction magnitude.

    Supports:
        amount
        credit
        debit
    """
    amount = numeric(transaction.get("amount"))

    if amount is not None:
        return abs(amount)

    credit = numeric(transaction.get("credit"))

    if credit is not None:
        return abs(credit)

    debit = numeric(transaction.get("debit"))

    if debit is not None:
        return abs(debit)

    return 0.0


def transaction_type(
    transaction: Mapping[str, Any]
) -> str:
    """
    Normalize transaction type.

    Supported:
        CR / CREDIT / C / IN
        DR / DEBIT / D / OUT
    """

    raw = str(
        transaction.get("type")
        or transaction.get("transaction_type")
        or ""
    ).strip().upper()

    if raw in {"CR", "CREDIT", "C", "IN"}:
        return "CREDIT"

    if raw in {"DR", "DEBIT", "D", "OUT"}:
        return "DEBIT"

    if numeric(transaction.get("credit")) not in (None, 0.0):
        return "CREDIT"

    if numeric(transaction.get("debit")) not in (None, 0.0):
        return "DEBIT"

    return ""


def _transaction_date(
    transaction: Mapping[str, Any]
) -> datetime | None:
    return parse_datetime(
        transaction.get("date")
        or transaction.get("transaction_date")
    )


def _transaction_balance(
    transaction: Mapping[str, Any]
) -> float | None:

    if "closing_balance" in transaction:
        return numeric(transaction.get("closing_balance"))

    return numeric(transaction.get("balance"))


def _flag(
    rule: str,
    message: str,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:

    return {
        "rule": rule,
        "weight": RULE_WEIGHTS[rule],
        "message": message,
        "evidence": dict(evidence or {}),
    }


# ============================================================
# IDENTITY HELPERS
# ============================================================

def _identity_values(
    record: Mapping[str, Any]
) -> dict[str, str]:

    values = {}

    for field in IDENTITY_FIELDS:

        normalized = normalize_identifier(
            record.get(field)
        )

        if normalized:
            values[field] = normalized

    return values


def _identity_matches(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> list[str]:

    first_values = _identity_values(first)
    second_values = _identity_values(second)

    matches = []

    for field in IDENTITY_FIELDS:

        if (
            field in first_values
            and field in second_values
            and first_values[field] == second_values[field]
        ):
            matches.append(field)

    return matches


# ============================================================
# IDENTITY / LOAN STACKING RULES
# ============================================================

def duplicate_identity(
    borrower: Mapping[str, Any],
    applications: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """
    Detect another application sharing a stable identity attribute.

    Matching fields:
        PAN
        phone number
        bank account
        borrower ID
    """

    matches = []

    for application in applications:

        if application is borrower:
            continue

        fields = _identity_matches(
            borrower,
            application
        )

        if fields:
            matches.append({
                "application_id": application.get(
                    "application_id"
                ),
                "matched_fields": fields,
            })

    if not matches:
        return None

    return _flag(
        "DUPLICATE_IDENTITY",
        "Another application matches the borrower's identity.",
        {
            "matches": matches
        }
    )


def multiple_recent_applications(
    borrower: Mapping[str, Any],
    applications: Sequence[Mapping[str, Any]],
    reference_time: Any = None,
    days: int = RECENT_APPLICATION_DAYS,
) -> dict[str, Any] | None:
    """
    Detect multiple matching applications within the
    recent application window.
    """

    reference = (
        parse_datetime(reference_time)
        or datetime.now()
    )

    matches = []

    for application in applications:

        if application is borrower:
            continue

        fields = _identity_matches(
            borrower,
            application
        )

        created = parse_datetime(
            application.get("application_date")
            or application.get("created_at")
        )

        if not fields or created is None:
            continue

        age = reference - created

        if timedelta(0) <= age <= timedelta(days=days):

            matches.append({
                "application_id": application.get(
                    "application_id"
                ),
                "application_date": created.isoformat(),
                "matched_fields": fields,
            })

    if len(matches) < 2:
        return None

    return _flag(
        "MULTIPLE_RECENT_APPLICATIONS",
        f"{len(matches)} matching applications "
        f"were submitted within {days} days.",
        {
            "window_days": days,
            "matches": matches,
        }
    )


def active_loan_overlap(
    borrower: Mapping[str, Any],
    applications: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """
    Detect multiple active/pending loan applications
    for the same identity.
    """

    matches = []

    for application in applications:

        if application is borrower:
            continue

        fields = _identity_matches(
            borrower,
            application
        )

        status = str(
            application.get("status", "")
        ).strip().upper()

        if (
            fields
            and status in ACTIVE_STATUSES
        ):
            matches.append({
                "application_id": application.get(
                    "application_id"
                ),
                "status": status,
                "matched_fields": fields,
            })

    if len(matches) < 2:
        return None

    return _flag(
        "ACTIVE_LOAN_OVERLAP",
        "Multiple active/pending loan applications "
        "share the same identity.",
        {
            "matches": matches
        }
    )


def rapid_reapplication(
    borrower: Mapping[str, Any],
    applications: Sequence[Mapping[str, Any]],
    reference_time: Any = None,
    days: int = RAPID_REAPPLICATION_DAYS,
) -> dict[str, Any] | None:
    """
    Detect another matching application submitted
    within the rapid-reapplication window.
    """

    reference = parse_datetime(reference_time)

    if reference is None:

        reference = parse_datetime(
            borrower.get("application_date")
            or borrower.get("created_at")
        )

    if reference is None:
        return None

    matches = []

    for application in applications:

        if application is borrower:
            continue

        fields = _identity_matches(
            borrower,
            application
        )

        created = parse_datetime(
            application.get("application_date")
            or application.get("created_at")
        )

        if not fields or created is None:
            continue

        difference_seconds = abs(
            (reference - created).total_seconds()
        )

        if (
            0 < difference_seconds
            <= days * 86400
        ):

            matches.append({
                "application_id": application.get(
                    "application_id"
                ),
                "application_date": created.isoformat(),
                "matched_fields": fields,
                "difference_hours": round(
                    difference_seconds / 3600,
                    2
                ),
            })

    if not matches:
        return None

    return _flag(
        "RAPID_REAPPLICATION",
        f"A matching application was submitted "
        f"within {days} days.",
        {
            "window_days": days,
            "matches": matches,
        }
    )


# ============================================================
# TRANSACTION ANOMALY RULES
# ============================================================

def large_deposit(
    transactions: Sequence[Mapping[str, Any]],
    multiplier: float = LARGE_DEPOSIT_MULTIPLIER,
) -> dict[str, Any] | None:
    """
    Detect unusually large incoming transactions relative
    to the account's median credit transaction.
    """

    credits = [
        transaction_amount(tx)
        for tx in transactions
        if transaction_type(tx) == "CREDIT"
    ]

    credits = [
        amount
        for amount in credits
        if amount > 0
    ]

    if len(credits) < 3:
        return None

    baseline = median(credits)

    if baseline <= 0:
        return None

    suspicious = []

    for transaction in transactions:

        if transaction_type(transaction) != "CREDIT":
            continue

        amount = transaction_amount(transaction)

        if amount >= multiplier * baseline:

            suspicious.append({
                "amount": amount,
                "date": str(
                    transaction.get("date")
                    or transaction.get("transaction_date")
                    or ""
                ),
            })

    if not suspicious:
        return None

    return _flag(
        "LARGE_DEPOSIT",
        f"Credit transaction is at least "
        f"{multiplier:.1f}x the median credit baseline.",
        {
            "median_credit": baseline,
            "multiplier": multiplier,
            "transactions": suspicious,
        }
    )


def sudden_balance_increase(
    transactions: Sequence[Mapping[str, Any]],
    multiplier: float = BALANCE_INCREASE_MULTIPLIER,
    min_percent: float = BALANCE_INCREASE_PERCENT,
) -> dict[str, Any] | None:
    """
    Detect sharp consecutive closing-balance increases.
    """

    observations = []

    for transaction in transactions:

        date = _transaction_date(transaction)
        balance = _transaction_balance(transaction)

        if date is not None and balance is not None:

            observations.append(
                (date, balance)
            )

    observations.sort(key=lambda item: item[0])

    suspicious = []

    for (
        previous,
        current
    ) in zip(
        observations,
        observations[1:]
    ):

        previous_date, previous_balance = previous
        current_date, current_balance = current

        if previous_balance <= 0:
            continue

        increase_percent = (
            (
                current_balance
                - previous_balance
            )
            / previous_balance
        ) * 100.0

        if (
            current_balance
            >= multiplier * previous_balance
            and increase_percent >= min_percent
        ):

            suspicious.append({
                "previous_date":
                    previous_date.isoformat(),

                "date":
                    current_date.isoformat(),

                "previous_balance":
                    previous_balance,

                "balance":
                    current_balance,

                "increase_percent":
                    round(increase_percent, 2),
            })

    if not suspicious:
        return None

    return _flag(
        "SUDDEN_BALANCE_INCREASE",
        "Closing balance increased sharply "
        "between consecutive observations.",
        {
            "transactions": suspicious,
            "multiplier": multiplier,
            "minimum_percent": min_percent,
        }
    )


def repeated_identical_transactions(
    transactions: Sequence[Mapping[str, Any]],
    minimum_count: int = REPEATED_TRANSACTION_COUNT,
) -> dict[str, Any] | None:
    """
    Detect repeated amount + type + narration patterns.
    """

    signatures = Counter()

    for transaction in transactions:

        amount = round(
            transaction_amount(transaction),
            2
        )

        tx_type = transaction_type(transaction)

        narration = str(
            transaction.get("narration")
            or ""
        ).strip().upper()

        if amount > 0 and tx_type:

            signatures[
                (
                    amount,
                    tx_type,
                    narration
                )
            ] += 1

    repeated = []

    for (
        signature,
        count
    ) in signatures.items():

        if count < minimum_count:
            continue

        amount, tx_type, narration = signature

        repeated.append({
            "amount": amount,
            "type": tx_type,
            "narration": narration,
            "count": count,
        })

    if not repeated:
        return None

    return _flag(
        "REPEATED_IDENTICAL_TRANSACTIONS",
        f"An identical transaction pattern occurred "
        f"at least {minimum_count} times.",
        {
            "patterns": repeated
        }
    )


def credit_debit_spike(
    transactions: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """
    Detect an unusually large transaction relative to the
    normal transaction amount distribution.

    Each candidate transaction is evaluated against a baseline
    calculated from the OTHER valid transactions. This prevents
    one extreme transaction from inflating its own baseline.

    A transaction is flagged when:

        amount > mean(other_transactions)
                 + SPIKE_ZSCORE * standard_deviation
    """

    valid_transactions = []

    for transaction in transactions:

        amount = transaction_amount(transaction)
        tx_type = transaction_type(transaction)
        tx_date = _transaction_date(transaction)

        if amount <= 0:
            continue

        if tx_type not in {"CREDIT", "DEBIT"}:
            continue

        valid_transactions.append({
            "date": tx_date,
            "amount": float(amount),
            "type": tx_type,
        })

    # Need enough observations to establish a meaningful baseline.
    if len(valid_transactions) < 4:
        return None

    spikes = []

    for index, candidate in enumerate(valid_transactions):

        # Exclude the candidate from its own baseline.
        baseline_transactions = [
            tx
            for position, tx in enumerate(valid_transactions)
            if position != index
        ]

        baseline_amounts = [
            tx["amount"]
            for tx in baseline_transactions
        ]

        if len(baseline_amounts) < 3:
            continue

        mean_amount = mean(baseline_amounts)
        std_amount = pstdev(baseline_amounts)

        # No variation means there is no meaningful
        # statistical spike to detect.
        if std_amount <= 0:
            continue

        threshold = (
            mean_amount
            + SPIKE_ZSCORE * std_amount
        )

        if candidate["amount"] <= threshold:
            continue

        z_score = (
            candidate["amount"] - mean_amount
        ) / std_amount

        spikes.append({
            "date": (
                candidate["date"].isoformat()
                if candidate["date"] is not None
                else None
            ),
            "amount": candidate["amount"],
            "type": candidate["type"],
            "mean_amount": mean_amount,
            "std_amount": std_amount,
            "threshold": threshold,
            "z_score": z_score,
        })

    if not spikes:
        return None

    return _flag(
        "CREDIT_DEBIT_SPIKE",
        (
            f"Transaction amount exceeds the normal "
            f"transaction level by more than "
            f"{SPIKE_ZSCORE:.1f} standard deviations."
        ),
        {
            "z_score_threshold": SPIKE_ZSCORE,
            "spikes": spikes,
        },
    )

def money_in_out_pattern(
    transactions: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """
    Detect cases where a substantial portion of an incoming
    transaction leaves the account shortly afterward.

    The debit must occur strictly within the configured
    time window.

    Exactly 24 hours does NOT count as within 24 hours.
    """

    credits = []
    debits = []

    for transaction in transactions:

        amount = transaction_amount(transaction)
        tx_type = transaction_type(transaction)
        tx_date = _transaction_date(transaction)

        if amount <= 0:
            continue

        if tx_date is None:
            continue

        amount = float(amount)

        if tx_type == "CREDIT":

            credits.append({
                "date": tx_date,
                "amount": amount,
            })

        elif tx_type == "DEBIT":

            debits.append({
                "date": tx_date,
                "amount": amount,
            })

    matches = []

    for credit in credits:

        for debit in debits:

            # Debit must happen after the credit.
            if debit["date"] <= credit["date"]:
                continue

            elapsed = (
                debit["date"]
                - credit["date"]
            )

            hours_after_credit = (
                elapsed.total_seconds() / 3600.0
            )

            # Strictly less than 24 hours.
            if hours_after_credit >= MONEY_OUT_WINDOW_HOURS:
                continue

            debit_ratio = (
                debit["amount"]
                / credit["amount"]
            )

            if debit_ratio < MONEY_OUT_RATIO:
                continue

            matches.append({
                "credit_date":
                    credit["date"].isoformat(),

                "credit_amount":
                    credit["amount"],

                "debit_date":
                    debit["date"].isoformat(),

                "debit_amount":
                    debit["amount"],

                "debit_ratio":
                    debit_ratio,

                "hours_after_credit":
                    hours_after_credit,
            })

    if not matches:
        return None

    return _flag(
        "MONEY_IN_OUT_PATTERN",
        (
            f"At least {MONEY_OUT_RATIO:.0%} of an incoming "
            f"amount leaves within {MONEY_OUT_WINDOW_HOURS} hours."
        ),
        {
            "window_hours":
                MONEY_OUT_WINDOW_HOURS,

            "minimum_out_ratio":
                MONEY_OUT_RATIO,

            "matches":
                matches,
        },
    )

def round_number_activity(
    transactions: Sequence[Mapping[str, Any]],
    minimum_amount: float = ROUND_NUMBER_MIN,
) -> dict[str, Any] | None:
    """
    Detect repeated large round-number transactions.

    Example:
        ₹10,000
        ₹20,000
        ₹50,000
    """

    suspicious = []

    for transaction in transactions:

        amount = transaction_amount(transaction)

        if (
            amount >= minimum_amount
            and math.isclose(
                amount % minimum_amount,
                0.0,
                abs_tol=0.01,
            )
        ):

            suspicious.append({
                "amount": amount,
                "type": transaction_type(transaction),
                "date": str(
                    transaction.get("date")
                    or transaction.get("transaction_date")
                    or ""
                ),
            })

    if len(suspicious) < 2:
        return None

    return _flag(
        "ROUND_NUMBER_ACTIVITY",
        f"At least two transactions are large "
        f"round-number amounts (>= {minimum_amount:g}).",
        {
            "minimum_amount": minimum_amount,
            "transactions": suspicious,
        }
    )


def abnormal_balance_behaviour(
    transactions: Sequence[Mapping[str, Any]],
    near_zero_threshold: float = NEAR_ZERO_BALANCE,
) -> dict[str, Any] | None:
    """
    Detect negative balances or repeated near-zero balances.
    """

    balances = []

    for transaction in transactions:

        balance = _transaction_balance(
            transaction
        )

        if balance is not None:

            balances.append({
                "balance": balance,
                "date": str(
                    transaction.get("date")
                    or transaction.get("transaction_date")
                    or ""
                ),
            })

    negative = [
        item
        for item in balances
        if item["balance"] < 0
    ]

    near_zero = [
        item
        for item in balances
        if 0 <= item["balance"] <= near_zero_threshold
    ]

    if (
        not negative
        and len(near_zero) < 2
    ):
        return None

    return _flag(
        "ABNORMAL_BALANCE_BEHAVIOUR",
        "Account balance shows negative or repeated "
        "near-zero observations.",
        {
            "negative_balance_count":
                len(negative),

            "near_zero_count":
                len(near_zero),

            "negative_balances":
                negative,

            "near_zero_balances":
                near_zero,
        }
    )


# ============================================================
# RULE GROUPS
# ============================================================

IDENTITY_RULES = (
    duplicate_identity,
    multiple_recent_applications,
    active_loan_overlap,
    rapid_reapplication,
)


TRANSACTION_RULES = (
    large_deposit,
    sudden_balance_increase,
    repeated_identical_transactions,
    credit_debit_spike,
    money_in_out_pattern,
    round_number_activity,
    abnormal_balance_behaviour,
)