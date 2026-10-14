"""Tests for the isolated, deterministic synthetic loan-stacking demo."""

import unittest
from unittest.mock import patch

from features.loan_stacking_demo import SCENARIOS, analyze_synthetic_obligations, scenario_result
from route.demo_loan_stacking import _require_demo_mode, get_scenario
from fastapi import HTTPException


class LoanStackingDemoTests(unittest.TestCase):
    def test_overlapping_payment_streams_are_a_caveated_signal(self):
        result = scenario_result("overlapping-obligations")
        self.assertEqual(result["status"], "POSSIBLE_OVERLAPPING_OBLIGATIONS")
        self.assertFalse(result["confirmed_loan_stacking"])
        self.assertEqual(len(result["candidate_obligations"]), 2)
        self.assertEqual(len(result["overlapping_months"]), 3)
        self.assertEqual(result["repayment_burden"]["monthly_obligations"], 22200)
        self.assertEqual(result["repayment_burden"]["obligation_to_income_ratio"], 0.3171)

    def test_repeated_instalments_for_one_reference_are_not_stacking(self):
        result = scenario_result("single-loan-repayments")
        self.assertEqual(result["status"], "SINGLE_RECURRING_OBLIGATION")
        self.assertEqual(len(result["candidate_obligations"]), 1)
        self.assertEqual(result["overlapping_months"], {})

    def test_duplicates_reversals_transfers_and_card_payments_do_not_create_obligations(self):
        result = scenario_result("duplicates-transfers")
        self.assertEqual(result["status"], "SINGLE_RECURRING_OBLIGATION")
        self.assertEqual(len(result["candidate_obligations"]), 1)
        excluded = result["excluded_or_uncertain_evidence"]
        self.assertEqual(excluded["duplicate_rows"], 1)
        self.assertEqual(excluded["reversals"], 2)
        self.assertEqual(excluded["transfers"], 1)
        self.assertEqual(excluded["credit_card_payments"], 1)

    def test_keywords_without_distinct_references_return_insufficient_evidence(self):
        result = scenario_result("insufficient-evidence")
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(result["repayment_burden"])
        self.assertEqual(result["excluded_or_uncertain_evidence"]["unlinked_debt_keywords"], 2)

    def test_repeated_non_debt_payments_do_not_become_loan_obligations(self):
        rows = [
            {"transaction_id": "SYN-U1", "date": "2026-08-05", "direction": "DR", "amount": 9800,
             "reference": "SYN-MANDATE-U1", "narration": "MONTHLY SERVICE"},
            {"transaction_id": "SYN-U2", "date": "2026-09-05", "direction": "DR", "amount": 9800,
             "reference": "SYN-MANDATE-U1", "narration": "MONTHLY SERVICE"},
        ]
        result = analyze_synthetic_obligations(rows, monthly_net_income=70000)
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["excluded_or_uncertain_evidence"]["referenced_non_debt_debits"], 2)
        self.assertIsNone(result["repayment_burden"])

    def test_income_is_required_for_burden_and_detector_does_not_mutate_input(self):
        source = [dict(row) for row in SCENARIOS["overlapping-obligations"]["transactions"]]
        before = [dict(row) for row in source]
        result = analyze_synthetic_obligations(source, monthly_net_income=None)
        self.assertIsNone(result["repayment_burden"])
        self.assertEqual(source, before)

    def test_demo_api_fails_closed_and_unknown_scenario_is_not_found(self):
        with patch.dict("os.environ", {"PRISM_ENV": "production", "PRISM_DEMO_FIXTURES": "true"}):
            with self.assertRaises(HTTPException) as blocked:
                _require_demo_mode()
            self.assertEqual(blocked.exception.status_code, 404)
        with patch.dict("os.environ", {"PRISM_ENV": "demo", "PRISM_DEMO_FIXTURES": "true"}):
            self.assertEqual(get_scenario("overlapping-obligations")["synthetic_demo"], True)
            with self.assertRaises(HTTPException) as unknown:
                get_scenario("real-applicant")
            self.assertEqual(unknown.exception.status_code, 404)

    def test_demo_api_is_read_only_and_separate_from_assessment_routes(self):
        from route.demo_loan_stacking import router
        self.assertEqual({method for route in router.routes for method in route.methods}, {"GET"})
        self.assertTrue(all(route.path.startswith("/demo/loan-stacking") for route in router.routes))


if __name__ == "__main__":
    unittest.main()
