import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agents.document_parser import DocumentParserAgent
from app.agents.enrichment_agent import EnrichmentAgent
from app.schemas.enrich import EnrichRequest, DocumentMeta

client = TestClient(app)


# ── Endpoint contract tests ─────────────────────────────────────────


def test_enrich_returns_suggestions():
    """POST /v1/enrich returns enrichment suggestions."""
    payload = {
        "case_id": 1,
        "request_id": "enrich-001",
        "documents": [
            {"filename": "RE-2024-00123_119.00.pdf", "mimetype": "application/pdf", "size_bytes": 1024},
        ],
        "context": {"partner_name": "Acme GmbH"},
    }
    response = client.post("/v1/enrich", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == 1
    assert data["request_id"] == "enrich-001"
    assert data["status"] == "ok"
    assert len(data["suggestions"]) > 0


def test_enrich_validates_input():
    """POST /v1/enrich rejects empty payload."""
    response = client.post("/v1/enrich", json={})
    assert response.status_code == 422


def test_enrich_empty_documents():
    """POST /v1/enrich with no documents still returns ok."""
    payload = {
        "case_id": 2,
        "request_id": "enrich-002",
        "documents": [],
        "context": {},
    }
    response = client.post("/v1/enrich", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["suggestions"], list)


def test_enrich_suggestion_schema():
    """Each enrichment suggestion has required fields with valid ranges."""
    payload = {
        "case_id": 3,
        "request_id": "enrich-003",
        "documents": [
            {"filename": "INV-20240115_250.00.pdf", "mimetype": "application/pdf"},
        ],
        "context": {},
    }
    response = client.post("/v1/enrich", json=payload)
    data = response.json()
    for suggestion in data["suggestions"]:
        assert "field" in suggestion
        assert "value" in suggestion
        assert "confidence" in suggestion
        assert 0 <= suggestion["confidence"] <= 1
        assert "source" in suggestion


# ── DocumentParserAgent unit tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_parser_extracts_date_from_filename():
    """DocumentParserAgent extracts dates from filenames."""
    agent = DocumentParserAgent()
    request = EnrichRequest(
        case_id=1,
        request_id="test",
        documents=[DocumentMeta(filename="RE_2024-01-15_acme.pdf", mimetype="application/pdf")],
    )
    results = await agent.run(request)
    date_suggestions = [s for s in results if s.field == "invoice_date"]
    assert len(date_suggestions) == 1
    assert "2024-01-15" in date_suggestions[0].value


@pytest.mark.asyncio
async def test_parser_extracts_invoice_number():
    """DocumentParserAgent extracts invoice numbers from filenames."""
    agent = DocumentParserAgent()
    request = EnrichRequest(
        case_id=1,
        request_id="test",
        documents=[DocumentMeta(filename="RE-00123.pdf", mimetype="application/pdf")],
    )
    results = await agent.run(request)
    inv_suggestions = [s for s in results if s.field == "invoice_number"]
    assert len(inv_suggestions) == 1
    assert "RE-00123" in inv_suggestions[0].value


@pytest.mark.asyncio
async def test_parser_extracts_amount():
    """DocumentParserAgent extracts amounts from filenames."""
    agent = DocumentParserAgent()
    request = EnrichRequest(
        case_id=1,
        request_id="test",
        documents=[DocumentMeta(filename="invoice_119.00.pdf", mimetype="application/pdf")],
    )
    results = await agent.run(request)
    amount_suggestions = [s for s in results if s.field == "amount_total"]
    assert len(amount_suggestions) == 1
    assert amount_suggestions[0].value == "119.00"


@pytest.mark.asyncio
async def test_parser_extracts_from_context():
    """DocumentParserAgent uses context for high-confidence suggestions."""
    agent = DocumentParserAgent()
    request = EnrichRequest(
        case_id=1,
        request_id="test",
        documents=[],
        context={"partner_name": "Test GmbH", "period": "2024-01"},
    )
    results = await agent.run(request)
    fields = {s.field for s in results}
    assert "partner_name" in fields
    assert "period" in fields


@pytest.mark.asyncio
async def test_enrichment_agent_deduplicates():
    """EnrichmentAgent keeps highest confidence per field."""
    agent = EnrichmentAgent()
    request = EnrichRequest(
        case_id=1,
        request_id="test",
        documents=[
            DocumentMeta(filename="2024-01-15_inv.pdf", mimetype="application/pdf"),
            DocumentMeta(filename="2024-02-20_inv.pdf", mimetype="application/pdf"),
        ],
    )
    results = await agent.run(request)
    date_results = [s for s in results if s.field == "invoice_date"]
    assert len(date_results) == 1


@pytest.mark.asyncio
async def test_enrichment_agent_sorted_by_confidence():
    """EnrichmentAgent returns suggestions sorted by confidence descending."""
    agent = EnrichmentAgent()
    request = EnrichRequest(
        case_id=1,
        request_id="test",
        documents=[
            DocumentMeta(filename="RE-00123_2024-01-15_119.00.pdf", mimetype="application/pdf"),
        ],
        context={"partner_name": "Sorted GmbH"},
    )
    results = await agent.run(request)
    confidences = [s.confidence for s in results]
    assert confidences == sorted(confidences, reverse=True)
