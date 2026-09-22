"""Deterministic integration coverage for the P1 assessment service."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from services.assessment_service import assess_borrower
from scoring.risk_scorer import score_borrower


REFERENCE_TIME = datetime(2026, 9, 18, 12, 0, 0)
CREDIT_INPUT = {
    "bank": {"credit_debit_ratio": 1.25, "cashflow_cv": 0.35, "min_balance_l3m": 25000},
    "salary": {"net_to_gross_ratio": 0.82},
    "utility": {"utility_stability": 0.20},
}


def application(application_id: str, **updates: object) -> dict:
    result = {
        "application_id": application_id,
        "pan": "ABCDE1234F",
        "phone_number": "9876543210",
        "bank_account": "1234567890",
        "application_date": REFERENCE_TIME.isoformat(),
        "status": "PENDING",
    }
    result.update(updates)
    return result


def transaction(date: str, amount: float, tx_type: str = "CR", **updates: object) -> dict:
    result = {"date": date, "amount": amount, "type": tx_type, "narration": ""}
    result.update(updates)
    return result


def rule_names(result: dict) -> set[str]:
    return {flag["rule"] for flag in result["fraud_risk"]["flags"]}


class IntegratedAssessmentTests(unittest.TestCase):
    def assess(self, **fraud_inputs: object) -> dict:
        return assess_borrower(**CREDIT_INPUT, reference_time=REFERENCE_TIME, **fraud_inputs)

    def assert_rule(self, expected: str, result: dict) -> None:
        self.assertIn(expected, rule_names(result))
        flag = next(item for item in result["fraud_risk"]["flags"] if item["rule"] == expected)
        self.assertIn(flag["category"], {"identity", "transaction"})
        self.assertIn(flag["severity"], {"low", "medium", "high"})
        self.assertIsInstance(flag["evidence"], dict)

    def test_clean_borrower_and_credit_regression(self) -> None:
        baseline = score_borrower(**CREDIT_INPUT)
        result = self.assess(borrower=application("APP-CLEAN"), application_history=[])
        self.assertEqual(result["score"], baseline["score"])
        self.assertEqual(result["pd"], baseline["pd"])
        self.assertEqual(result["risk_tier"], baseline["risk_tier"])
        self.assertEqual(result["fraud_risk"]["fraud_score"], 0)
        self.assertEqual(result["fraud_risk"]["fraud_status"], "CLEAR")

    def test_identity_and_loan_stacking_rules(self) -> None:
        borrower = application("APP-NEW")
        duplicate = application("APP-OLD")
        result = self.assess(borrower=borrower, application_history=[duplicate])
        self.assert_rule("DUPLICATE_IDENTITY", result)

        stacking = self.assess(borrower=borrower, application_history=[
            application("APP-1", application_date=(REFERENCE_TIME - timedelta(days=2)).isoformat(), status="ACTIVE"),
            application("APP-2", application_date=(REFERENCE_TIME - timedelta(days=10)).isoformat(), status="DISBURSED"),
        ])
        self.assert_rule("MULTIPLE_RECENT_APPLICATIONS", stacking)
        self.assert_rule("ACTIVE_LOAN_OVERLAP", stacking)

        rapid = self.assess(borrower=borrower, application_history=[
            application("APP-RAPID", application_date=(REFERENCE_TIME - timedelta(days=3)).isoformat()),
        ])
        self.assert_rule("RAPID_REAPPLICATION", rapid)

    def test_transaction_anomaly_rules(self) -> None:
        cases = {
            "LARGE_DEPOSIT": [transaction("2026-09-01", 1000), transaction("2026-09-02", 1200), transaction("2026-09-03", 1100), transaction("2026-09-04", 5000)],
            "SUDDEN_BALANCE_INCREASE": [transaction("2026-09-01", 1000, closing_balance=5000), transaction("2026-09-02", 1000, closing_balance=12000)],
            "REPEATED_IDENTICAL_TRANSACTIONS": [transaction(f"2026-09-0{i}", 25000, narration="SALARY") for i in range(1, 4)],
            "CREDIT_DEBIT_SPIKE": [transaction(f"2026-09-{i:02d}", 1000 + i * 10) for i in range(1, 8)] + [transaction("2026-09-20", 100000, "DR")],
            "MONEY_IN_OUT_PATTERN": [transaction("2026-09-01T10:00:00", 100000), transaction("2026-09-01T18:00:00", 85000, "DR")],
            "ROUND_NUMBER_ACTIVITY": [transaction("2026-09-01", 10000), transaction("2026-09-02", 20000, "DR")],
            "ABNORMAL_BALANCE_BEHAVIOUR": [transaction("2026-09-01", 1000, "DR", closing_balance=500), transaction("2026-09-02", 1000, "DR", closing_balance=800), transaction("2026-09-03", 1000, "DR", closing_balance=-200)],
        }
        for expected, transactions in cases.items():
            with self.subTest(rule=expected):
                self.assert_rule(expected, self.assess(transactions=transactions))

    def test_multi_flag_score_is_capped(self) -> None:
        result = self.assess(
            borrower=application("APP-NEW"),
            application_history=[
                application("APP-1", status="ACTIVE", application_date=(REFERENCE_TIME - timedelta(days=2)).isoformat()),
                application("APP-2", status="DISBURSED", application_date=(REFERENCE_TIME - timedelta(days=5)).isoformat()),
            ],
            transactions=[transaction("2026-09-01", 1000), transaction("2026-09-02", 1100), transaction("2026-09-03", 1000), transaction("2026-09-04", 5000)],
        )
        fraud = result["fraud_risk"]
        self.assertGreaterEqual(fraud["rule_count"], 3)
        self.assertLessEqual(fraud["fraud_score"], 100)
        self.assertEqual(fraud["fraud_score"], min(100, sum(flag["weight"] for flag in fraud["flags"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
