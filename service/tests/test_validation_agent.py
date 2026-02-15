import pytest

from app.agents.validation_agent import ValidationAgent
from app.schemas.orchestrate import OrchestrateRequest, Suggestion


@pytest.fixture
def agent():
    return ValidationAgent()


def _make_request(context=None):
    return OrchestrateRequest(
        case_id=1,
        request_id="test",
        context=context or {},
    )


def _make_suggestion(lines=None, confidence=0.9, risk_score=0.1):
    """Create a valid accounting_entry suggestion for testing."""
    if lines is None:
        lines = [
            {"account": "6300", "debit": 100.0, "credit": 0.0, "description": "Aufwand"},
            {"account": "1576", "debit": 19.0, "credit": 0.0, "description": "Vorsteuer 19%"},
            {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "Verbindlichkeiten"},
        ]
    return Suggestion(
        suggestion_type="accounting_entry",
        payload={"lines": lines},
        confidence=confidence,
        risk_score=risk_score,
        explanation="Test",
        requires_human=True,
        agent_name="kontierung_agent",
    )


# ── Happy path ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_pass_balanced_entry(agent):
    """Balanced entry with good scores passes validation."""
    request = _make_request()
    suggestions = [_make_suggestion()]
    results = await agent.run(request, suggestions)
    assert len(results) == 1
    assert results[0].payload["status"] == "pass"
    assert results[0].payload["errors"] == []
    assert results[0].confidence == 1.0
    assert results[0].requires_human is False


@pytest.mark.asyncio
async def test_validation_result_structure(agent):
    """Validation result has correct type and agent name."""
    request = _make_request()
    results = await agent.run(request, [_make_suggestion()])
    assert results[0].suggestion_type == "validation"
    assert results[0].agent_name == "validation_agent"


# ── Balance checks ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_fail_unbalanced(agent):
    """Unbalanced entry fails validation."""
    lines = [
        {"account": "6300", "debit": 100.0, "credit": 0.0, "description": "Aufwand"},
        {"account": "1600", "debit": 0.0, "credit": 50.0, "description": "Verbindlichkeiten"},
    ]
    request = _make_request()
    results = await agent.run(request, [_make_suggestion(lines=lines)])
    assert results[0].payload["status"] == "fail"
    assert any("not balanced" in e for e in results[0].payload["errors"])


# ── Line completeness ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_fail_missing_account(agent):
    """Line without account code fails validation."""
    lines = [
        {"account": "", "debit": 100.0, "credit": 0.0, "description": "Bad"},
        {"account": "1600", "debit": 0.0, "credit": 100.0, "description": "OK"},
    ]
    request = _make_request()
    results = await agent.run(request, [_make_suggestion(lines=lines)])
    assert results[0].payload["status"] == "fail"
    assert any("missing account" in e for e in results[0].payload["errors"])


@pytest.mark.asyncio
async def test_validation_fail_zero_amounts(agent):
    """Line with zero debit and credit fails validation."""
    lines = [
        {"account": "6300", "debit": 0.0, "credit": 0.0, "description": "Bad"},
        {"account": "1600", "debit": 0.0, "credit": 0.0, "description": "Bad"},
    ]
    request = _make_request()
    results = await agent.run(request, [_make_suggestion(lines=lines)])
    assert results[0].payload["status"] == "fail"
    assert any("debit or credit must be > 0" in e for e in results[0].payload["errors"])


@pytest.mark.asyncio
async def test_validation_warn_missing_description(agent):
    """Line without description produces a warning (not error)."""
    lines = [
        {"account": "6300", "debit": 119.0, "credit": 0.0},
        {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "OK"},
    ]
    request = _make_request()
    results = await agent.run(request, [_make_suggestion(lines=lines)])
    # Should pass (warnings don't cause failure)
    assert results[0].payload["status"] == "pass"
    assert any("missing description" in w for w in results[0].payload["warnings"])


# ── Threshold checks ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_fail_high_risk(agent):
    """Risk score exceeding policy max fails validation."""
    request = _make_request({
        "policies": [
            {"scope": "company", "key": "default", "rules": {"risk_score_max": 0.3}},
        ],
    })
    results = await agent.run(request, [_make_suggestion(risk_score=0.5)])
    assert results[0].payload["status"] == "fail"
    assert any("Risk score" in e for e in results[0].payload["errors"])


@pytest.mark.asyncio
async def test_validation_warn_low_confidence(agent):
    """Confidence below threshold produces a warning."""
    request = _make_request({
        "policies": [
            {"scope": "company", "key": "default", "rules": {"confidence_threshold": 0.9}},
        ],
    })
    results = await agent.run(request, [_make_suggestion(confidence=0.7)])
    assert any("Confidence" in w for w in results[0].payload["warnings"])


# ── Edge cases ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_no_suggestions(agent):
    """Empty suggestions list fails validation."""
    request = _make_request()
    results = await agent.run(request, [])
    assert results[0].payload["status"] == "fail"
    assert any("No accounting entry" in e for e in results[0].payload["errors"])


@pytest.mark.asyncio
async def test_validation_invalid_account_code(agent):
    """Non-numeric account code produces a warning."""
    lines = [
        {"account": "abc", "debit": 119.0, "credit": 0.0, "description": "Bad"},
        {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "OK"},
    ]
    request = _make_request()
    results = await agent.run(request, [_make_suggestion(lines=lines)])
    assert any("not a valid number" in w for w in results[0].payload["warnings"])
