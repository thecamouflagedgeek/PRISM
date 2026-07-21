from datetime import datetime, timedelta
import uuid

_sessions = {}
TTL_MINUTES = 60


class Session:
    def __init__(
        self,
        borrower_id: str,
        user_id: int = None,
        application_id: int = None
    ):
        self.session_id = str(uuid.uuid4())

        self.borrower_id = borrower_id
        self.phone_number = borrower_id

        # Database identifiers
        self.user_id = user_id
        self.application_id = application_id

        self.is_authenticated = True

        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(minutes=TTL_MINUTES)

        # Consent
        self.consent_bank = False
        self.consent_salary = False
        self.consent_utility = False
        self.consent_dpdpa = False

        # Data cache
        self.bank_features = None
        self.salary_features = None
        self.utility_features = None

        # Confidence
        self.bank_conf = 0.0
        self.salary_conf = 0.0
        self.utility_conf = 0.0

        self.result = None

    def expired(self):
        return datetime.utcnow() > self.expires_at


def create_session(
    borrower_id: str,
    user_id: int = None,
    application_id: int = None
):
    s = Session(
        borrower_id=borrower_id,
        user_id=user_id,
        application_id=application_id
    )

    _sessions[s.session_id] = s

    return s


def get_session(session_id: str):
    s = _sessions.get(session_id)

    if not s:
        return None

    if s.expired():
        del _sessions[session_id]
        return None

    return s