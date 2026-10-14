"""Ensure first-login persistence failures roll back instead of leaving a user."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from auth import service
from database.models import Application


class AuthAtomicityTests(unittest.TestCase):
    def test_missing_audit_storage_rolls_back_first_login(self):
        db = Mock()
        db.query.return_value.filter.return_value.all.return_value = []
        user = SimpleNamespace(user_id=17)
        application = SimpleNamespace(application_id=29)
        with patch.object(service, "verify_otp", return_value=True), \
             patch.object(service, "get_user_by_phone", return_value=None), \
             patch.object(service, "create_user", return_value=user) as create_user, \
             patch.object(service, "create_application", return_value=application) as create_application, \
             patch.object(service, "save_audit_event", side_effect=RuntimeError("audit storage unavailable")), \
             patch.object(service, "create_session") as create_session:
            with self.assertRaisesRegex(RuntimeError, "audit storage unavailable"):
                service.verify(db, "synthetic-test-recipient", "123456")
        create_user.assert_called_once_with(db, "synthetic-test-recipient", commit=False)
        create_application.assert_called_once_with(db, user.user_id, commit=False)
        db.rollback.assert_called_once_with()
        db.commit.assert_not_called()
        create_session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
