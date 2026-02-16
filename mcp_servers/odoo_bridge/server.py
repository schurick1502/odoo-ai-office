"""Odoo AI Office MCP Server – exposes account_ai_office via XML-RPC as MCP tools."""

import json

from mcp.server.fastmcp import FastMCP

from .client import OdooAiOfficeClient

mcp = FastMCP("odoo-ai-office")
_client: OdooAiOfficeClient | None = None


def _get_client() -> OdooAiOfficeClient:
    global _client
    if _client is None:
        _client = OdooAiOfficeClient()
    return _client


@mcp.tool()
def odoo_health() -> str:
    """Check Odoo connectivity and return version info."""
    result = _get_client().health()
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def odoo_list_cases(
    state: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List AI Office cases with optional state filter.

    Args:
        state: Filter by state (new, enriched, proposed, approved, posted, exported)
        limit: Max results (default 50)
        offset: Skip first N results
    """
    result = _get_client().list_cases(state=state, limit=limit, offset=offset)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def odoo_get_case(case_id: int) -> str:
    """Get full details of an AI Office case.

    Args:
        case_id: Odoo case record ID
    """
    result = _get_client().get_case(case_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def odoo_create_case(
    partner_name: str | None = None,
    partner_email: str | None = None,
    period: str | None = None,
    source_model: str | None = None,
    source_id: int | None = None,
) -> str:
    """Create a new AI Office case. Matches or creates partner automatically.

    Args:
        partner_name: Supplier/partner name (will be matched or created)
        partner_email: Partner email for matching
        period: Accounting period (e.g. '2024-01')
        source_model: Source system identifier (e.g. 'docflow.job')
        source_id: Source record ID for deduplication
    """
    vals = {}
    if partner_name:
        vals["partner_name"] = partner_name
    if partner_email:
        vals["partner_email"] = partner_email
    if period:
        vals["period"] = period
    if source_model:
        vals["source_model"] = source_model
    if source_id is not None:
        vals["source_id"] = source_id

    case_id = _get_client().create_case(vals)
    return json.dumps({"case_id": case_id, "status": "created"}, indent=2)


@mcp.tool()
def odoo_add_suggestion(
    case_id: int,
    suggestion_type: str,
    payload: str,
    confidence: float,
    risk_score: float,
    explanation: str,
    agent_name: str,
) -> str:
    """Add a suggestion to an existing AI Office case.

    Args:
        case_id: Target case ID
        suggestion_type: Type (accounting_entry, enrichment, classification, validation, reconciliation)
        payload: JSON string with suggestion data (lines, amounts, etc.)
        confidence: Confidence score 0.0-1.0
        risk_score: Risk score 0.0-1.0
        explanation: Human-readable explanation
        agent_name: Name of the agent that generated this suggestion
    """
    try:
        payload_data = json.loads(payload) if isinstance(payload, str) else payload
    except (json.JSONDecodeError, TypeError):
        payload_data = {}

    suggestion_id = _get_client().add_suggestion(case_id, {
        "suggestion_type": suggestion_type,
        "payload": payload_data,
        "confidence": confidence,
        "risk_score": risk_score,
        "explanation": explanation,
        "agent_name": agent_name,
    })
    return json.dumps({"suggestion_id": suggestion_id, "status": "created"}, indent=2)


@mcp.tool()
def odoo_propose_case(case_id: int) -> str:
    """Transition an AI Office case to 'proposed' state.

    Args:
        case_id: Case ID to propose
    """
    _get_client().action_propose(case_id)
    return json.dumps({"case_id": case_id, "state": "proposed"}, indent=2)


@mcp.tool()
def odoo_approve_case(case_id: int) -> str:
    """Approve an AI Office case (requires approver permissions, runs GoBD validation).

    Args:
        case_id: Case ID to approve
    """
    _get_client().action_approve(case_id)
    return json.dumps({"case_id": case_id, "state": "approved"}, indent=2)


@mcp.tool()
def odoo_post_case(case_id: int) -> str:
    """Post an AI Office case (creates account.move journal entry).

    Args:
        case_id: Case ID to post
    """
    _get_client().action_post(case_id)
    return json.dumps({"case_id": case_id, "state": "posted"}, indent=2)


@mcp.tool()
def odoo_export_case(case_id: int) -> str:
    """Export an AI Office case to DATEV format.

    Args:
        case_id: Case ID to export
    """
    _get_client().action_export(case_id)
    return json.dumps({"case_id": case_id, "state": "exported"}, indent=2)


@mcp.tool()
def odoo_get_suggestions(case_id: int) -> str:
    """Get all suggestions for an AI Office case.

    Args:
        case_id: Case ID
    """
    result = _get_client().get_suggestions(case_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def odoo_search_partners(query: str) -> str:
    """Search Odoo partners by name or email.

    Args:
        query: Search string (matches name and email)
    """
    result = _get_client().search_partners(query)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def odoo_list_audit_logs(case_id: int) -> str:
    """Get the audit trail for an AI Office case.

    Args:
        case_id: Case ID
    """
    result = _get_client().list_audit_logs(case_id)
    return json.dumps(result, indent=2, default=str)


def main():
    """Run the Odoo AI Office MCP server (STDIO transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
