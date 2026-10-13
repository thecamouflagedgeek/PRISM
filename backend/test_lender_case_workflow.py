from datetime import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.session_store import create_session
from database.db import engine, get_db
from database.models import Application, User
from main import app


@pytest.fixture
def postgres_demo():
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    phone = f"+1999{uuid.uuid4().int % 10**10:010d}"
    user = User(phone=phone, created_at=datetime.utcnow())
    db.add(user)
    db.flush()
    application = Application(user_id=user.user_id,
        application_date=datetime(2026, 10, 1), application_status="IN_PROGRESS")
    db.add(application)
    db.flush()
    db.commit()
    borrower = create_session(phone, user_id=user.user_id,
        application_id=application.application_id, role="borrower")
    lender = create_session("synthetic-lender", user_id=None,
        application_id=None, role="lender")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield {"client": TestClient(app), "db": db, "user": user,
            "application": application, "borrower": borrower, "lender": lender}
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        outer.rollback()
        connection.close()


def test_lender_case_actions_are_persisted_and_return_in_case_history(postgres_demo):
    state = postgres_demo
    application_id = state["application"].application_id
    headers = {"session-id": state["lender"].session_id}
    client = state["client"]

    listed = client.get("/lender/applications", headers=headers)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["applications"]
               if item["application_id"] == application_id)
    assert row["review"]["review_status"] == "NEW"

    assigned = client.post(f"/lender/applications/{application_id}/case-updates",
        headers=headers, json={"action":"assign_to_me"})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["review"]["assigned_to"] == state["lender"].phone_number
    assert assigned.json()["review"]["review_status"] == "IN_REVIEW"

    noted = client.post(f"/lender/applications/{application_id}/case-updates",
        headers=headers, json={"action":"add_note", "note":"Verified uploaded evidence list."})
    assert noted.status_code == 200, noted.text

    requested = client.post(f"/lender/applications/{application_id}/case-updates",
        headers=headers, json={"action":"request_information",
            "requested_information":["Complete statement page 2"]})
    assert requested.status_code == 200, requested.text
    assert requested.json()["review"]["review_status"] == "AWAITING_DOCUMENTS"

    detail = client.get(f"/lender/applications/{application_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    result = detail.json()
    assert result["review"]["requested_information"] == ["Complete statement page 2"]
    assert any(event["action"] == "lender_application_viewed" for event in result["review_history"])
    assert any(event["note"] == "Verified uploaded evidence list." for event in result["review_history"])


def test_lender_case_update_requires_lender_role(postgres_demo):
    state = postgres_demo
    response = state["client"].post(
        f"/lender/applications/{state['application'].application_id}/case-updates",
        headers={"session-id": state["borrower"].session_id},
        json={"action":"assign_to_me"})
    assert response.status_code == 403
