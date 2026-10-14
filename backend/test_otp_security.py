"""Focused OTP security tests; no OTP values are written to test output."""

import io
import logging
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from fastapi import HTTPException

from auth import service
from auth.otp import generate_otp, verify_otp
from auth.store import otp_store


class OtpSecurityTests(unittest.TestCase):
    def tearDown(self):
        otp_store.pop("synthetic-test-recipient", None)

    def test_otp_is_six_digits_and_uses_secure_random_source(self):
        with patch.dict(os.environ, {}, clear=True), patch("auth.otp.secrets.randbelow", return_value=899999) as randbelow:
            otp = generate_otp("synthetic-test-recipient")
        self.assertRegex(otp, r"^\d{6}$")
        self.assertEqual(otp, "999999")
        randbelow.assert_called_once_with(900000)

    def test_generation_writes_no_authentication_data_to_stdout(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch("auth.otp.secrets.randbelow", return_value=0), redirect_stdout(output):
            otp = generate_otp("synthetic-test-recipient")
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(otp, output.getvalue())
        self.assertNotIn("synthetic-test-recipient", output.getvalue())

    def test_otp_expires_and_verifies_without_printing_it(self):
        with patch.dict(os.environ, {}, clear=True), patch("auth.otp.secrets.randbelow", return_value=123456):
            otp = generate_otp("synthetic-test-recipient")
        self.assertTrue(verify_otp("synthetic-test-recipient", otp))
        self.assertFalse(verify_otp("synthetic-test-recipient", otp))

    def test_local_development_logs_only_labeled_otp_and_api_message_is_honest(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger("auth.otp")
        logger.addHandler(handler)
        try:
            with patch.dict(os.environ, {"PRISM_ENV": "development", "PRISM_OTP_LOGGING": "true"}, clear=True), \
                 patch("auth.otp.secrets.randbelow", return_value=123456):
                response = service.signup(Mock(), "synthetic-test-recipient")
        finally:
            logger.removeHandler(handler)
            handler.close()

        logged = output.getvalue()
        self.assertIn("DEVELOPMENT-ONLY OTP: 223456", logged)
        self.assertNotIn("synthetic-test-recipient", logged)
        self.assertNotIn("223456", response["message"])
        self.assertIn("No SMS was sent", response["message"])

    def test_production_and_unconfigured_modes_fail_without_logging_or_storing_otp(self):
        for env in (
            {"PRISM_ENV": "production", "PRISM_OTP_LOGGING": "true"},
            {"PRISM_ENV": "test", "PRISM_OTP_LOGGING": "true"},
            {"PRISM_ENV": "development"},
            {},
        ):
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True), \
                 patch("auth.otp.secrets.randbelow") as randbelow:
                with self.assertRaises(HTTPException) as caught:
                    service.signup(Mock(), "synthetic-test-recipient")
                self.assertEqual(caught.exception.status_code, 503)
                randbelow.assert_not_called()
                self.assertNotIn("synthetic-test-recipient", otp_store)

    def test_pytest_process_never_enables_otp_logging(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger("auth.otp")
        logger.addHandler(handler)
        try:
            with patch.dict(os.environ, {"PRISM_ENV": "development", "PRISM_OTP_LOGGING": "true",
                                         "PYTEST_CURRENT_TEST": "test-otp-policy"}, clear=True), \
                 patch("auth.otp.secrets.randbelow", return_value=1):
                otp = generate_otp("synthetic-test-recipient")
        finally:
            logger.removeHandler(handler)
            handler.close()
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(otp, output.getvalue())


if __name__ == "__main__":
    unittest.main()
