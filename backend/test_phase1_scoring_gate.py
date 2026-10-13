import unittest
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from scoring import risk_scorer


GOOD_EVIDENCE = {
    "bank": {"available": True, "extraction_status": "SUCCESS", "quality_score": 0.9,
             "transaction_count": 20, "history_days": 120, "age_days": 20},
    "salary": {"available": True, "extraction_status": "SUCCESS", "quality_score": 0.9},
    "utility": {"available": True, "extraction_status": "SUCCESS", "quality_score": 0.9, "observation_count": 3},
}
GOOD_FEATURES = {
    "bank": {"credit_debit_ratio": 0.0, "cashflow_cv": 0.0, "min_balance_l3m": 0.0},
    "salary": {"net_to_gross_ratio": 0.0}, "utility": {"utility_stability": 0.0},
}


class ScoringGateTests(unittest.TestCase):
    def test_all_features_missing_never_scores(self):
        result = risk_scorer.score_borrower()
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["display_score"])
        self.assertIsNone(result["pd"])

    def test_one_valid_feature_is_still_insufficient(self):
        result = risk_scorer.score_borrower(bank={"credit_debit_ratio": 0}, evidence=GOOD_EVIDENCE)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["display_score"])

    def test_out_of_range_feature_is_rejected(self):
        invalid_bank = {**GOOD_FEATURES["bank"], "credit_debit_ratio": -1}
        result = risk_scorer.score_borrower(bank=invalid_bank, salary=GOOD_FEATURES["salary"],
            utility=GOOD_FEATURES["utility"], evidence=GOOD_EVIDENCE)
        self.assertEqual(result["feature_states"]["credit_debit_ratio"]["validation_status"], "OUT_OF_RANGE")
        self.assertIsNone(result["display_score"])

    def test_extraction_failure_blocks_model(self):
        evidence = {**GOOD_EVIDENCE, "bank": {**GOOD_EVIDENCE["bank"], "extraction_status": "FAILED"}}
        result = risk_scorer.score_borrower(**GOOD_FEATURES, evidence=evidence)
        self.assertIsNone(result["display_score"])
        self.assertIn("bank_extraction_failed", result["data_sufficiency"]["reasons"])

    def test_missing_salary_document_blocks_complete_features(self):
        evidence = {**GOOD_EVIDENCE, "salary": {"available": False, "extraction_status": "FAILED", "quality_score": 0}}
        result = risk_scorer.score_borrower(**GOOD_FEATURES, evidence=evidence)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["pd"])
        self.assertIsNone(result["display_score"])
        self.assertIn("salary_document_unavailable", result["data_sufficiency"]["reasons"])

    def test_fewer_than_three_utility_observations_blocks_score(self):
        evidence = {**GOOD_EVIDENCE, "utility": {**GOOD_EVIDENCE["utility"], "observation_count": 2}}
        result = risk_scorer.score_borrower(**GOOD_FEATURES, evidence=evidence)
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["display_score"])
        self.assertIn("insufficient_utility_history", result["data_sufficiency"]["reasons"])

    def test_valid_zero_is_distinct_from_missing_and_can_score(self):
        result = risk_scorer.score_borrower(**GOOD_FEATURES, evidence=GOOD_EVIDENCE)
        self.assertEqual(result["status"], "SCORED")
        self.assertEqual(result["feature_states"]["credit_debit_ratio"]["validation_status"], "VALID")
        missing = risk_scorer.score_borrower(**{**GOOD_FEATURES, "salary": {}}, evidence=GOOD_EVIDENCE)
        self.assertEqual(missing["feature_states"]["net_to_gross_ratio"]["validation_status"], "UNAVAILABLE")
        self.assertIsNone(missing["display_score"])

    def test_score_decreases_as_pd_increases_and_clipping_is_reported(self):
        low_pd_score = risk_scorer._score_trace(-1.0)["raw_score_unclipped"]
        high_pd_score = risk_scorer._score_trace(1.0)["raw_score_unclipped"]
        self.assertGreater(risk_scorer._compute_pd(1.0), risk_scorer._compute_pd(-1.0))
        self.assertGreater(low_pd_score, high_pd_score)
        base = risk_scorer._score_trace(-__import__("math").log(20))
        self.assertAlmostEqual(base["raw_score_unclipped"], 600)
        doubled_odds = risk_scorer._score_trace(-__import__("math").log(40))
        self.assertAlmostEqual(doubled_odds["raw_score_unclipped"] - base["raw_score_unclipped"], 50)
        clipped = risk_scorer._score_trace(100.0)
        self.assertTrue(clipped["clipping_occurred"])
        self.assertEqual(clipped["display_score"], 300)
        self.assertLess(clipped["raw_score_unclipped"], clipped["display_score"])

    def test_active_model_orders_control_vectors_and_reports_clipping(self):
        good = risk_scorer.score_borrower(
            bank={"credit_debit_ratio": 5, "cashflow_cv": .2, "min_balance_l3m": 50000},
            salary={"net_to_gross_ratio": .9}, utility={"utility_stability": .3}, evidence=GOOD_EVIDENCE)
        stressed = risk_scorer.score_borrower(
            bank={"credit_debit_ratio": .5, "cashflow_cv": .9, "min_balance_l3m": 100},
            salary={"net_to_gross_ratio": .5}, utility={"utility_stability": .8}, evidence=GOOD_EVIDENCE)
        self.assertGreater(stressed["raw_pd"], good["raw_pd"])
        self.assertLess(stressed["display_score"], good["display_score"])
        self.assertTrue(stressed["clipping_occurred"])
        self.assertEqual(stressed["display_score"], 300)
        self.assertLess(stressed["raw_score_unclipped"], 300)

    def test_score_reconstruction_and_manifest_schema(self):
        result = risk_scorer.score_borrower(**GOOD_FEATURES, evidence=GOOD_EVIDENCE)
        self.assertAlmostEqual(result["raw_score_unclipped"], result["score_calculation"]["reconstructed_raw_score"])
        self.assertEqual(result["model_validation_status"], "UNVERIFIED_REAL_WORLD")
        self.assertEqual(result["phase_1_runtime_status"], "VERIFIED")
        self.assertEqual(risk_scorer.MODEL_MANIFEST["feature_schema"], [
            "credit_debit_ratio", "cashflow_cv", "net_to_gross_ratio", "utility_stability", "min_balance"])
        self.assertEqual(set(risk_scorer.MODEL_MANIFEST["artifacts"]), {"lr_model.pkl", "binning.pkl"})
        artifact_dir = Path(risk_scorer._ARTIFACTS)
        for name, expected_hash in risk_scorer.MODEL_MANIFEST["artifacts"].items():
            actual_hash = hashlib.sha256((artifact_dir / name).read_bytes()).hexdigest()
            self.assertEqual(actual_hash, expected_hash)
        self.assertNotIn("score", result)
        self.assertNotIn("risk_score", result)
        self.assertNotIn("confidence_score", result)
        self.assertNotIn("shap_reasons", result)
        self.assertIn("reason_codes", result)

    def test_startup_rejects_artifact_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copy2(Path(risk_scorer.__file__), root / "risk_scorer.py")
            artifacts = root / "artifacts"
            artifacts.mkdir()
            source = Path(risk_scorer._ARTIFACTS)
            for name in ("lr_model.pkl", "binning.pkl"):
                shutil.copy2(source / name, artifacts / name)
            manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8-sig"))
            manifest["artifacts"]["lr_model.pkl"] = "0" * 64
            (artifacts / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            process = subprocess.run([sys.executable, "-c", "import risk_scorer"], cwd=root,
                capture_output=True, text=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("Active artifact hash mismatch: lr_model.pkl", process.stderr)

    def test_sufficiency_reasons_include_history_and_staleness(self):
        evidence = {**GOOD_EVIDENCE, "bank": {**GOOD_EVIDENCE["bank"], "history_days": 20, "age_days": 365}}
        result = risk_scorer.score_borrower(**GOOD_FEATURES, evidence=evidence)
        self.assertIn("insufficient_statement_history", result["data_sufficiency"]["reasons"])
        self.assertIn("bank_document_stale", result["data_sufficiency"]["reasons"])
        self.assertIsNone(result["display_score"])

    def test_document_quality_scenarios_return_trace_without_score_assertions(self):
        for label, ratio, cv, quality in (("good", 1.4, 0.25, 0.95),
                                          ("moderate", 1.0, 0.55, 0.75),
                                          ("stressed", 0.5, 0.9, 0.85)):
            with self.subTest(label=label):
                evidence = {**GOOD_EVIDENCE,
                    "bank": {**GOOD_EVIDENCE["bank"], "quality_score": quality},
                    "salary": {**GOOD_EVIDENCE["salary"], "quality_score": quality},
                    "utility": {**GOOD_EVIDENCE["utility"], "quality_score": quality}}
                features = {**GOOD_FEATURES,
                    "bank": {**GOOD_FEATURES["bank"], "credit_debit_ratio": ratio, "cashflow_cv": cv}}
                result = risk_scorer.score_borrower(**features, evidence=evidence)
                self.assertEqual(result["status"], "SCORED")
                self.assertIn("woe_features", result)
                self.assertIn("bin_indices", result)
                self.assertIn("score_calculation", result)


if __name__ == "__main__":
    unittest.main()
