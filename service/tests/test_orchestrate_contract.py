from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_orchestrate_returns_suggestions():
    payload = {
        "case_id": 1,
        "request_id": "test-001",
        "context": {}
    }
    response = client.post("/v1/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == 1
    assert data["request_id"] == "test-001"
    assert len(data["suggestions"]) > 0

    suggestion = data["suggestions"][0]
    assert "suggestion_type" in suggestion
    assert "payload" in suggestion
    assert "confidence" in suggestion
    assert 0 <= suggestion["confidence"] <= 1
    assert "risk_score" in suggestion
    assert "requires_human" in suggestion
    assert "agent_name" in suggestion


def test_orchestrate_validates_input():
    response = client.post("/v1/orchestrate", json={})
    assert response.status_code == 422


def test_orchestrate_schema_completeness():
    payload = {
        "case_id": 42,
        "request_id": "schema-test",
        "context": {"period": "2024-01"}
    }
    response = client.post("/v1/orchestrate", json=payload)
    data = response.json()
    assert data["status"] == "ok"
    for s in data["suggestions"]:
        assert isinstance(s["payload"], dict)
        assert isinstance(s["explanation"], str)
