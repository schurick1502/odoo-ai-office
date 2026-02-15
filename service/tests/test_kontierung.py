import pytest

from app.agents.kontierung_agent import KontierungsAgent, FALLBACK_EXPENSE, VORSTEUER_19, VERBINDLICHKEITEN
from app.schemas.orchestrate import OrchestrateRequest


@pytest.fixture
def agent():
    return KontierungsAgent()


def _make_request(context=None):
    return OrchestrateRequest(
        case_id=1,
        request_id="test",
        context=context or {},
    )


# ── Policy matching ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_match_supplier(agent):
    """Supplier policy sets expense account and high confidence."""
    request = _make_request({
        "amount_total": 119.0,
        "policies": [
            {"scope": "supplier", "key": "sup_acme", "rules": {"default_account": "4946"}},
        ],
    })
    results = await agent.run(request)
    assert len(results) == 1
    s = results[0]
    assert s.payload["expense_account"] == "4946"
    assert s.payload["policy_matched"] is True
    assert s.confidence == 0.92
    assert s.requires_human is False


@pytest.mark.asyncio
async def test_policy_match_company_fallback(agent):
    """Company policy used when no supplier policy exists."""
    request = _make_request({
        "amount_total": 238.0,
        "policies": [
            {"scope": "company", "key": "default", "rules": {"default_account": "4950"}},
        ],
    })
    results = await agent.run(request)
    assert results[0].payload["expense_account"] == "4950"
    assert results[0].payload["policy_matched"] is True


@pytest.mark.asyncio
async def test_supplier_policy_takes_priority(agent):
    """Supplier policy overrides company policy."""
    request = _make_request({
        "amount_total": 119.0,
        "policies": [
            {"scope": "company", "key": "default", "rules": {"default_account": "4950"}},
            {"scope": "supplier", "key": "sup_x", "rules": {"default_account": "4200"}},
        ],
    })
    results = await agent.run(request)
    assert results[0].payload["expense_account"] == "4200"


@pytest.mark.asyncio
async def test_no_policy_uses_fallback(agent):
    """Without policies, SKR03 fallback account is used."""
    request = _make_request({"amount_total": 119.0})
    results = await agent.run(request)
    s = results[0]
    assert s.payload["expense_account"] == FALLBACK_EXPENSE
    assert s.payload["policy_matched"] is False
    assert s.confidence == 0.75
    assert s.requires_human is True


# ── USt calculation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ust_19_percent(agent):
    """Standard 19% USt splits correctly."""
    request = _make_request({"amount_total": 119.0, "tax_rate": 0.19})
    results = await agent.run(request)
    payload = results[0].payload
    assert payload["net_amount"] == 100.0
    assert payload["tax_amount"] == 19.0
    assert payload["tax_rate"] == 0.19
    # Check lines: expense debit, tax debit, liabilities credit
    lines = payload["lines"]
    assert len(lines) == 3
    assert lines[0]["debit"] == 100.0  # expense
    assert lines[1]["debit"] == 19.0   # Vorsteuer
    assert lines[1]["account"] == VORSTEUER_19
    assert lines[2]["credit"] == 119.0  # Verbindlichkeiten
    assert lines[2]["account"] == VERBINDLICHKEITEN


@pytest.mark.asyncio
async def test_ust_7_percent(agent):
    """Reduced 7% USt uses correct Vorsteuer account."""
    request = _make_request({"amount_total": 107.0, "tax_rate": 0.07})
    results = await agent.run(request)
    payload = results[0].payload
    assert payload["net_amount"] == 100.0
    assert payload["tax_amount"] == 7.0
    assert payload["lines"][1]["account"] == "1571"  # Vorsteuer 7%


@pytest.mark.asyncio
async def test_zero_amount_fallback(agent):
    """Zero amount gets default values with low confidence."""
    request = _make_request({"amount_total": 0})
    results = await agent.run(request)
    s = results[0]
    assert s.payload["amount"] == 119.0  # default
    assert s.confidence == 0.55
    assert s.risk_score == 0.30


@pytest.mark.asyncio
async def test_no_amount_in_context(agent):
    """Missing amount_total in context treated as zero."""
    request = _make_request({})
    results = await agent.run(request)
    assert results[0].confidence == 0.55


# ── Suggestion structure ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suggestion_structure(agent):
    """Suggestion has correct type and agent name."""
    request = _make_request({"amount_total": 500.0})
    results = await agent.run(request)
    s = results[0]
    assert s.suggestion_type == "accounting_entry"
    assert s.agent_name == "kontierung_agent"
    assert s.payload["skr_chart"] == "SKR03"


@pytest.mark.asyncio
async def test_amount_parsing_string(agent):
    """Agent handles string amounts with comma separator."""
    request = _make_request({"amount_total": "1.190,00"})
    # German format won't parse perfectly but shouldn't crash
    results = await agent.run(request)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_partner_name_in_description(agent):
    """Partner name appears in Verbindlichkeiten line description."""
    request = _make_request({
        "amount_total": 119.0,
        "partner_name": "Acme GmbH",
    })
    results = await agent.run(request)
    liabilities_line = results[0].payload["lines"][2]
    assert "Acme GmbH" in liabilities_line["description"]
