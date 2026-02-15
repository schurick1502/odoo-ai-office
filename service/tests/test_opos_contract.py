from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_opos_match_returns_200():
    payload = {
        "case_id": 1,
        "request_id": "opos-001",
        "context": {
            "open_lines": [
                {"id": 1, "date": "2024-01-15", "ref": "RE-001", "name": "", "balance": 119.0, "amount_residual": 119.0},
                {"id": 2, "date": "2024-01-10", "ref": "RE-001", "name": "", "balance": -119.0, "amount_residual": -119.0},
            ],
        },
    }
    response = client.post("/v1/opos/match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == 1
    assert data["request_id"] == "opos-001"
    assert len(data["suggestions"]) > 0


def test_opos_match_validates_input():
    response = client.post("/v1/opos/match", json={})
    assert response.status_code == 422


def test_opos_match_empty_lines():
    payload = {
        "case_id": 2,
        "request_id": "opos-002",
        "context": {"open_lines": []},
    }
    response = client.post("/v1/opos/match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["suggestions"][0]["payload"]["matches"] == []


def test_opos_match_schema_complete():
    payload = {
        "case_id": 3,
        "request_id": "opos-003",
        "context": {"open_lines": []},
    }
    response = client.post("/v1/opos/match", json=payload)
    data = response.json()
    assert data["status"] == "ok"
    assert data["case_id"] == 3
    assert data["request_id"] == "opos-003"
    s = data["suggestions"][0]
    assert "suggestion_type" in s
    assert "payload" in s
    assert "confidence" in s
    assert "risk_score" in s
    assert "explanation" in s
    assert "requires_human" in s
    assert "agent_name" in s


def test_opos_match_reconciliation_type():
    payload = {
        "case_id": 4,
        "request_id": "opos-004",
        "context": {"open_lines": []},
    }
    response = client.post("/v1/opos/match", json=payload)
    data = response.json()
    for s in data["suggestions"]:
        assert s["suggestion_type"] == "reconciliation"


def test_opos_match_with_matching_lines():
    payload = {
        "case_id": 5,
        "request_id": "opos-005",
        "context": {
            "open_lines": [
                {"id": 10, "date": "2024-01-01", "ref": "", "name": "", "balance": 250.0, "amount_residual": 250.0},
                {"id": 20, "date": "2024-01-05", "ref": "", "name": "", "balance": -250.0, "amount_residual": -250.0},
            ],
        },
    }
    response = client.post("/v1/opos/match", json=payload)
    data = response.json()
    matches = data["suggestions"][0]["payload"]["matches"]
    assert len(matches) == 1
    assert matches[0]["debit_line_id"] == 10
    assert matches[0]["credit_line_id"] == 20


def test_opos_match_payload_structure():
    payload = {
        "case_id": 6,
        "request_id": "opos-006",
        "context": {"open_lines": []},
    }
    response = client.post("/v1/opos/match", json=payload)
    data = response.json()
    p = data["suggestions"][0]["payload"]
    assert "matches" in p
    assert "unmatched_debit" in p
    assert "unmatched_credit" in p


def test_opos_match_requires_human():
    payload = {
        "case_id": 7,
        "request_id": "opos-007",
        "context": {"open_lines": []},
    }
    response = client.post("/v1/opos/match", json=payload)
    data = response.json()
    for s in data["suggestions"]:
        assert s["requires_human"] is True
