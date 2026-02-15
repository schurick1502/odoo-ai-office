import pytest

from app.agents.opos_agent import OPOSMatchingAgent
from app.schemas.orchestrate import OrchestrateRequest


@pytest.fixture
def agent():
    return OPOSMatchingAgent()


def _req(open_lines=None):
    return OrchestrateRequest(
        case_id=1,
        request_id="opos-test",
        context={"open_lines": open_lines or []},
    )


# ── Basic scenarios ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_open_lines(agent):
    result = await agent.run(_req([]))
    assert len(result) == 1
    s = result[0]
    assert s.suggestion_type == "reconciliation"
    assert s.confidence == 0.0
    assert s.payload["matches"] == []


@pytest.mark.asyncio
async def test_exact_amount_match(agent):
    lines = [
        {"id": 1, "date": "2024-01-15", "ref": "", "name": "Zahlung", "balance": 119.0, "amount_residual": 119.0},
        {"id": 2, "date": "2024-01-10", "ref": "", "name": "Rechnung", "balance": -119.0, "amount_residual": -119.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 1
    assert matches[0]["match_type"] == "exact_amount"
    assert matches[0]["confidence"] >= 0.80
    assert matches[0]["amount"] == 119.0


@pytest.mark.asyncio
async def test_combined_match_amount_and_ref(agent):
    lines = [
        {"id": 1, "date": "2024-01-15", "ref": "RE-00123", "name": "", "balance": 200.0, "amount_residual": 200.0},
        {"id": 2, "date": "2024-01-10", "ref": "RE-00123", "name": "", "balance": -200.0, "amount_residual": -200.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 1
    assert matches[0]["match_type"] == "combined"
    assert matches[0]["confidence"] >= 0.95


@pytest.mark.asyncio
async def test_reference_only_match(agent):
    lines = [
        {"id": 1, "date": "2024-01-15", "ref": "RE-00456", "name": "", "balance": 100.0, "amount_residual": 100.0},
        {"id": 2, "date": "2024-01-10", "ref": "RE-00456", "name": "", "balance": -50.0, "amount_residual": -50.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 1
    assert matches[0]["match_type"] == "reference"
    assert matches[0]["confidence"] >= 0.60


@pytest.mark.asyncio
async def test_no_match_different_amounts_no_ref(agent):
    lines = [
        {"id": 1, "date": "2024-01-15", "ref": "", "name": "", "balance": 100.0, "amount_residual": 100.0},
        {"id": 2, "date": "2024-01-10", "ref": "", "name": "", "balance": -50.0, "amount_residual": -50.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 0
    assert result[0].payload["unmatched_debit"] == [1]
    assert result[0].payload["unmatched_credit"] == [2]


# ── Multiple matches ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_multiple_matches(agent):
    lines = [
        {"id": 1, "date": "2024-01-01", "ref": "", "name": "", "balance": 100.0, "amount_residual": 100.0},
        {"id": 2, "date": "2024-01-02", "ref": "", "name": "", "balance": 200.0, "amount_residual": 200.0},
        {"id": 3, "date": "2024-01-03", "ref": "", "name": "", "balance": 300.0, "amount_residual": 300.0},
        {"id": 4, "date": "2024-01-01", "ref": "", "name": "", "balance": -100.0, "amount_residual": -100.0},
        {"id": 5, "date": "2024-01-02", "ref": "", "name": "", "balance": -200.0, "amount_residual": -200.0},
        {"id": 6, "date": "2024-01-03", "ref": "", "name": "", "balance": -300.0, "amount_residual": -300.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 3


@pytest.mark.asyncio
async def test_line_used_only_once(agent):
    """Each line can only be used in one match."""
    lines = [
        {"id": 1, "date": "2024-01-01", "ref": "", "name": "", "balance": 100.0, "amount_residual": 100.0},
        {"id": 2, "date": "2024-01-02", "ref": "", "name": "", "balance": -100.0, "amount_residual": -100.0},
        {"id": 3, "date": "2024-01-03", "ref": "", "name": "", "balance": -100.0, "amount_residual": -100.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 1
    # One credit line remains unmatched
    assert len(result[0].payload["unmatched_credit"]) == 1


@pytest.mark.asyncio
async def test_combined_takes_priority(agent):
    """Combined match (amount+ref) is preferred over exact_amount."""
    lines = [
        {"id": 1, "date": "2024-01-01", "ref": "RE-001", "name": "", "balance": 100.0, "amount_residual": 100.0},
        {"id": 2, "date": "2024-01-02", "ref": "RE-001", "name": "", "balance": -100.0, "amount_residual": -100.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 1
    assert matches[0]["match_type"] == "combined"


# ── Output structure ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unmatched_ids_reported(agent):
    lines = [
        {"id": 10, "date": "2024-01-01", "ref": "", "name": "", "balance": 100.0, "amount_residual": 100.0},
        {"id": 20, "date": "2024-01-01", "ref": "", "name": "", "balance": 200.0, "amount_residual": 200.0},
        {"id": 30, "date": "2024-01-01", "ref": "", "name": "", "balance": -100.0, "amount_residual": -100.0},
    ]
    result = await agent.run(_req(lines))
    assert result[0].payload["unmatched_debit"] == [20]
    assert result[0].payload["unmatched_credit"] == []


@pytest.mark.asyncio
async def test_suggestion_structure(agent):
    lines = [
        {"id": 1, "date": "2024-01-01", "ref": "", "name": "", "balance": 50.0, "amount_residual": 50.0},
        {"id": 2, "date": "2024-01-01", "ref": "", "name": "", "balance": -50.0, "amount_residual": -50.0},
    ]
    result = await agent.run(_req(lines))
    s = result[0]
    assert s.suggestion_type == "reconciliation"
    assert s.agent_name == "opos_agent"
    assert s.requires_human is True
    assert "matches" in s.payload
    assert "unmatched_debit" in s.payload
    assert "unmatched_credit" in s.payload


@pytest.mark.asyncio
async def test_amount_tolerance(agent):
    """Amounts within 0.01 tolerance are considered equal."""
    lines = [
        {"id": 1, "date": "2024-01-01", "ref": "", "name": "", "balance": 100.005, "amount_residual": 100.005},
        {"id": 2, "date": "2024-01-01", "ref": "", "name": "", "balance": -100.0, "amount_residual": -100.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_ref_normalization(agent):
    """Reference normalization: 'RE-00123' matches 're_00123'."""
    lines = [
        {"id": 1, "date": "2024-01-01", "ref": "RE-00123", "name": "", "balance": 100.0, "amount_residual": 100.0},
        {"id": 2, "date": "2024-01-01", "ref": "re_00123", "name": "", "balance": -100.0, "amount_residual": -100.0},
    ]
    result = await agent.run(_req(lines))
    matches = result[0].payload["matches"]
    assert len(matches) == 1
    assert matches[0]["match_type"] == "combined"
