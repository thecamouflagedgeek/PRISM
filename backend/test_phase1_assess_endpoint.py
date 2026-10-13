"""HTTP integration checks for the active upload-to-assessment endpoint."""
import json
from pathlib import Path
import socket
import threading
import time
import urllib.request
import uuid
import unittest

import uvicorn

from core.session_store import create_session
from main import app


ROOT = Path(__file__).parent


class AssessEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="critical"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.1)
        if not cls.server.started:
            raise RuntimeError("Test ASGI server failed to start")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def post_assess(self, bank_bytes, utility_bytes=None):
        session = create_session("phase1-endpoint-test")
        session.consent_bank = True
        session.consent_utility = utility_bytes is not None
        boundary = "----PRISM" + uuid.uuid4().hex
        parts = []
        files = [("bank_file", "bank.pdf", bank_bytes)]
        if utility_bytes is not None:
            files.append(("utility_file", "utility.pdf", utility_bytes))
        for field, filename, content in files:
            parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
                "Content-Type: application/pdf\r\n\r\n").encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/assess", data=b"".join(parts), method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "session-id": session.session_id})
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.status, json.loads(response.read())

    def test_machine_readable_stale_bank_document_is_insufficient(self):
        bank = (ROOT / "temp" / "HDFC_Bank_Statement.pdf").read_bytes()
        http_status, body = self.post_assess(bank)
        self.assertEqual(http_status, 200)
        self.assertEqual(body["status"], "INSUFFICIENT_EXPERIMENTAL_EVIDENCE")
        self.assertIsNone(body["pd"])
        self.assertIsNone(body["display_score"])
        self.assertIn("CREDIT_CARD_STATEMENT_AND_REPAYMENT_HISTORY_REQUIRED", body["data_sufficiency"]["reasons"])
        self.assertIn("bank_document_stale", body["warnings"])
        self.assertEqual(body["extraction"]["bank"]["method"], "native_text")

    def test_scanned_utility_uses_ocr_but_still_gates_on_history_and_quality(self):
        bank = (ROOT / "temp" / "HDFC_Bank_Statement.pdf").read_bytes()
        scanned_utility = (ROOT / "temp" / "12.pdf").read_bytes()
        http_status, body = self.post_assess(bank, scanned_utility)
        self.assertEqual(http_status, 200)
        self.assertEqual(body["status"], "INSUFFICIENT_EXPERIMENTAL_EVIDENCE")
        self.assertIsNone(body["pd"])
        metadata = body["extraction"]["utility"]
        self.assertTrue(metadata["ocr_used"])
        self.assertGreater(metadata["ocr_confidence"], 0)
        self.assertIn("insufficient_utility_history", body["warnings"])
        self.assertIn("utility_extraction_quality_low", body["warnings"])

    def test_malformed_document_returns_no_score(self):
        http_status, body = self.post_assess(b"not a valid PDF")
        self.assertEqual(http_status, 200)
        self.assertEqual(body["status"], "INSUFFICIENT_EXPERIMENTAL_EVIDENCE")
        self.assertIsNone(body["pd"])
        self.assertIsNone(body["display_score"])
        self.assertIn("bank_extraction_failed", body["warnings"])
        self.assertIn("warning", body["extraction"]["bank"])

    def test_response_uses_canonical_frontend_fields(self):
        bank = (ROOT / "temp" / "HDFC_Bank_Statement.pdf").read_bytes()
        _, body = self.post_assess(bank)
        for field in ("application_id", "assessment_id", "assessment_status", "model_version", "score",
                      "probability_of_default", "risk_tier", "feature_coverage", "feature_values",
                      "woe_values", "feature_contributions", "reason_codes", "improvement_recommendations",
                      "document_findings", "fraud_findings", "assessment_timestamp", "display_score",
                      "status", "data_sufficiency", "extraction", "warnings", "supporting_intelligence"):
            self.assertIn(field, body)
        self.assertEqual(body["assessment_status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(body["score"])
        self.assertIsNone(body["probability_of_default"])
        self.assertIsNone(body["risk_tier"])
        self.assertEqual(body["feature_coverage"], 0.0)
        self.assertNotIn("confidence", body)
        for alias in ("risk_score", "confidence_score", "shap_reasons"):
            self.assertNotIn(alias, body)


if __name__ == "__main__":
    unittest.main()
