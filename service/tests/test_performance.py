"""Performance baseline tests.

These tests verify that endpoint response times stay within acceptable bounds.
They run in CI as part of the regular test suite to catch regressions.
"""

import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

MAX_HEALTH_MS = 50
MAX_ORCHESTRATE_MS = 200
MAX_ENRICH_MS = 200


def _measure_ms(fn) -> float:
    """Measure execution time of a callable in milliseconds."""
    start = time.monotonic()
    fn()
    return (time.monotonic() - start) * 1000


def test_health_performance():
    """Health endpoint responds within 50ms."""
    elapsed = _measure_ms(lambda: client.get("/health"))
    assert elapsed < MAX_HEALTH_MS, (
        f"Health took {elapsed:.1f}ms (max {MAX_HEALTH_MS}ms)"
    )


def test_orchestrate_performance():
    """Orchestrate endpoint responds within 200ms."""
    payload = {
        "case_id": 1,
        "request_id": "perf-001",
        "context": {"amount_total": 119.00},
    }
    elapsed = _measure_ms(lambda: client.post("/v1/orchestrate", json=payload))
    assert elapsed < MAX_ORCHESTRATE_MS, (
        f"Orchestrate took {elapsed:.1f}ms (max {MAX_ORCHESTRATE_MS}ms)"
    )


def test_enrich_performance():
    """Enrich endpoint responds within 200ms."""
    payload = {
        "case_id": 1,
        "request_id": "perf-002",
        "documents": [
            {
                "filename": "RE-2024-00123_119.00.pdf",
                "mimetype": "application/pdf",
                "size_bytes": 1024,
            },
        ],
        "context": {},
    }
    elapsed = _measure_ms(lambda: client.post("/v1/enrich", json=payload))
    assert elapsed < MAX_ENRICH_MS, (
        f"Enrich took {elapsed:.1f}ms (max {MAX_ENRICH_MS}ms)"
    )
