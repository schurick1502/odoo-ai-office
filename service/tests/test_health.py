from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_includes_checks():
    """Health response includes component checks."""
    response = client.get("/health")
    data = response.json()
    assert "checks" in data
    assert "self" in data["checks"]
    assert data["checks"]["self"]["status"] == "ok"


def test_metrics_endpoint():
    """Prometheus /metrics endpoint is exposed."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "HELP" in response.text or "http_request" in response.text
