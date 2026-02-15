"""Load test scenarios for AI Office Service.

Run with:
    locust -f service/tests/load/locustfile.py --host http://localhost:8100

Web UI: http://localhost:8089
Headless: locust -f ... --headless -u 50 -r 5 --run-time 60s
"""

from locust import HttpUser, between, task


class AIServiceUser(HttpUser):
    """Simulates typical API usage patterns."""

    wait_time = between(0.5, 2.0)

    @task(5)
    def health_check(self):
        """GET /health - most frequent call (monitoring)."""
        self.client.get("/health")

    @task(3)
    def orchestrate(self):
        """POST /v1/orchestrate - primary business endpoint."""
        self.client.post(
            "/v1/orchestrate",
            json={
                "case_id": 1,
                "request_id": "load-test-001",
                "context": {
                    "amount_total": 119.00,
                    "tax_rate": 0.19,
                    "partner_name": "Test GmbH",
                    "policies": [],
                },
            },
        )

    @task(2)
    def enrich(self):
        """POST /v1/enrich - document enrichment."""
        self.client.post(
            "/v1/enrich",
            json={
                "case_id": 1,
                "request_id": "load-test-002",
                "documents": [
                    {
                        "filename": "RE-2024-00123_119.00.pdf",
                        "mimetype": "application/pdf",
                        "size_bytes": 1024,
                    }
                ],
                "context": {"partner_name": "Test GmbH"},
            },
        )

    @task(1)
    def opos_match(self):
        """POST /v1/opos/match - OPOS reconciliation."""
        self.client.post(
            "/v1/opos/match",
            json={
                "case_id": 1,
                "request_id": "load-test-003",
                "context": {
                    "open_lines": [
                        {
                            "id": 1,
                            "date": "2024-01-15",
                            "ref": "INV-001",
                            "name": "Invoice",
                            "balance": 119.00,
                            "amount_residual": 119.00,
                            "account_code": "1600",
                            "move_name": "BILL/2024/001",
                        },
                        {
                            "id": 2,
                            "date": "2024-01-20",
                            "ref": "INV-001",
                            "name": "Payment",
                            "balance": -119.00,
                            "amount_residual": -119.00,
                            "account_code": "1600",
                            "move_name": "BNK/2024/001",
                        },
                    ],
                    "partner_name": "Test GmbH",
                },
            },
        )

    @task(1)
    def metrics(self):
        """GET /metrics - Prometheus scrape."""
        self.client.get("/metrics")
