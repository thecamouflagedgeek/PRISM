from datetime import datetime, timedelta
import uuid

_sessions = {}
TTL_MINUTES = 60


class Session:
    def __init__(self, borrower_id: str):
        self.session_id = str(uuid.uuid4())
        self.borrower_id = borrower_id
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(minutes=TTL_MINUTES)

        # consent
        self.consent_bank = False
        self.consent_salary = False
        self.consent_utility = False
        self.consent_dpdpa = False

        # data cache
        self.bank_features = None
        self.salary_features = None
        self.utility_features = None

        # confidence
        self.bank_conf = 0.0
        self.salary_conf = 0.0
        self.utility_conf = 0.0

        self.result = None

    def expired(self):
        return datetime.utcnow() > self.expires_at


def create_session(borrower_id: str):
    s = Session(borrower_id)
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