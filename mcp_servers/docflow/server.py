"""DocumentFlow MCP Server – exposes DocumentFlow REST API as MCP tools."""

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from .client import DocFlowClient

mcp = FastMCP("docflow-bridge")
_client: DocFlowClient | None = None


def _get_client() -> DocFlowClient:
    global _client
    if _client is None:
        _client = DocFlowClient()
    return _client


@mcp.tool()
async def docflow_health() -> str:
    """Check DocumentFlow service health."""
    result = await _get_client().health()
    return json.dumps(result, indent=2)


@mcp.tool()
async def docflow_list_jobs(
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> str:
    """List DocumentFlow jobs with optional status filter.

    Args:
        status: Filter by status (e.g. 'approved', 'classified', 'exported')
        page: Page number (default 1)
        page_size: Results per page (default 50)
    """
    result = await _get_client().list_jobs(status=status, page=page, page_size=page_size)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def docflow_get_job(job_id: int) -> str:
    """Get a DocumentFlow job with full document_data (sender, invoice, amounts, etc).

    Args:
        job_id: The DocumentFlow job ID
    """
    result = await _get_client().get_job(job_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def docflow_get_bookings(job_id: int) -> str:
    """Get Soll/Haben booking entries for a DocumentFlow job.

    Args:
        job_id: The DocumentFlow job ID
    """
    result = await _get_client().get_bookings(job_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def docflow_get_positions(job_id: int) -> str:
    """Get extracted invoice line items (positions) for a DocumentFlow job.

    Args:
        job_id: The DocumentFlow job ID
    """
    result = await _get_client().get_positions(job_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def docflow_approve_job(job_id: int) -> str:
    """Approve a classified DocumentFlow job for export.

    Args:
        job_id: The DocumentFlow job ID to approve
    """
    result = await _get_client().approve_job(job_id)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def docflow_export_datev(month: str) -> str:
    """Trigger DATEV export for a specific month in DocumentFlow.

    Args:
        month: Month in YYYY-MM format (e.g. '2024-01')
    """
    result = await _get_client().export_datev(month)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
async def docflow_search_jobs(query: str) -> str:
    """Full-text search across DocumentFlow jobs.

    Args:
        query: Search query string (matches sender, invoice number, etc.)
    """
    result = await _get_client().search_jobs(query)
    return json.dumps(result, indent=2, default=str)


def main():
    """Run the DocumentFlow MCP server (STDIO transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
