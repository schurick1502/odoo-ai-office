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


def test_orchestrate_includes_validation_suggestion():
    """Orchestrate response includes a validation-type suggestion."""
    payload = {
        "case_id": 1,
        "request_id": "val-001",
        "context": {"amount_total": 119.0},
    }
    response = client.post("/v1/orchestrate", json=payload)
    assert response.status_code == 200
    data = response.json()
    types = [s["suggestion_type"] for s in data["suggestions"]]
    assert "accounting_entry" in types
    assert "validation" in types


def test_orchestrate_validation_has_status():
    """Validation suggestion payload contains status field."""
    payload = {
        "case_id": 2,
        "request_id": "val-002",
        "context": {"amount_total": 119.0},
    }
    response = client.post("/v1/orchestrate", json=payload)
    data = response.json()
    val_suggestions = [
        s for s in data["suggestions"] if s["suggestion_type"] == "validation"
    ]
    assert len(val_suggestions) == 1
    assert val_suggestions[0]["payload"]["status"] in ("pass", "fail")


def test_orchestrate_validation_with_strict_policies():
    """Validation respects strict policy thresholds from context."""
    payload = {
        "case_id": 3,
        "request_id": "val-003",
        "context": {
            "amount_total": 119.0,
            "policies": [
                {
                    "scope": "company",
                    "key": "default_threshold",
                    "rules": {
                        "confidence_threshold": 0.99,
                        "risk_score_max": 0.01,
                    },
                },
            ],
        },
    }
    response = client.post("/v1/orchestrate", json=payload)
    data = response.json()
    val = [s for s in data["suggestions"] if s["suggestion_type"] == "validation"][0]
    # With strict thresholds, the default kontierung should produce warnings or errors
    assert len(val["payload"]["warnings"]) > 0 or len(val["payload"]["errors"]) > 0
