from features.portfolio_sentiment import audit_sentiment_dataset, portfolio_sentiment_status


def test_sentiment_portfolio_output_is_unavailable_without_validated_inputs():
    result = portfolio_sentiment_status()
    assert result["status"] == "UNAVAILABLE"
    assert result["sentiment_classification"] is None
    assert result["portfolio_aggregate"] is None
    assert result["evaluation"] is None
    assert result["decision_use"] == "NOT_FOR_CREDIT_DECISION"
    assert len(result["required_before_enablement"]) >= 3


def test_existing_binary_labels_are_not_misrepresented_as_sentiment(tmp_path):
    dataset = tmp_path / "synthetic-only.csv"
    dataset.write_text("loan_description,label\nfictional text,0\nother fictional text,1\n", encoding="utf-8")
    result = audit_sentiment_dataset(dataset)
    assert result["status"] == "INVALID_LABELS"
    assert result["label_counts"] == {"0": 1, "1": 1}
    assert result["evaluation"] is None
    assert "fictional text" not in str(result)


def test_sentiment_audit_requires_documented_provenance_and_never_returns_examples(tmp_path):
    dataset = tmp_path / "synthetic-only.csv"
    dataset.write_text("loan_description,label\nfictional text,positive\n", encoding="utf-8")
    result = audit_sentiment_dataset(dataset)
    assert result["status"] == "UNAVAILABLE"
    assert result["provenance_complete"] is False
    assert "fictional text" not in str(result)


def test_portfolio_sentiment_api_is_lender_authenticated_and_returns_unavailable():
    from fastapi.testclient import TestClient
    from core.session_store import create_session, _sessions
    from main import app

    borrower = create_session("synthetic-sentiment-borrower", user_id=901, role="borrower")
    lender = create_session("synthetic-sentiment-lender", user_id=902, role="lender")
    try:
        with TestClient(app) as client:
            assert client.get("/lender/portfolio/sentiment").status_code == 401
            assert client.get("/lender/portfolio/sentiment", headers={"session-id": borrower.session_id}).status_code == 403
            response = client.get("/lender/portfolio/sentiment", headers={"session-id": lender.session_id})
        assert response.status_code == 200
        assert response.json()["status"] == "UNAVAILABLE"
        assert response.json()["portfolio_aggregate"] is None
    finally:
        _sessions.pop(borrower.session_id, None)
        _sessions.pop(lender.session_id, None)
