"""Tests for the DocumentFlow MCP server and client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from docflow.client import DocFlowClient
from tests.conftest import (
    SAMPLE_BOOKINGS,
    SAMPLE_JOB,
    SAMPLE_JOBS_LIST,
    SAMPLE_POSITIONS,
)


# ── Client Tests ────────────────────────────────────────────


class TestDocFlowClient:
    """Test DocFlowClient with mocked HTTP responses."""

    @pytest.fixture
    def client(self):
        return DocFlowClient(
            base_url="http://test:8000",
            token="test-jwt-token",
        )

    async def test_health(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.health()
            assert result["status"] == "ok"

    async def test_list_jobs(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_JOBS_LIST
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.list_jobs(status="approved")
            assert result["total"] == 1
            assert result["items"][0]["id"] == 42

    async def test_get_job(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_JOB
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.get_job(42)
            assert result["id"] == 42
            assert result["document_data"]["sender_name"] == "Test Lieferant GmbH"

    async def test_get_bookings(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_BOOKINGS
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.get_bookings(42)
            assert len(result) == 2
            assert result[0]["debit_account"] == "6300"

    async def test_get_positions(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_POSITIONS
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.get_positions(42)
            assert len(result) == 2
            assert result[0]["description"] == "Druckerpapier A4"

    async def test_approve_job(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {**SAMPLE_JOB, "status": "approved"}
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.approve_job(42)
            assert result["status"] == "approved"

    async def test_search_jobs(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_JOBS_LIST
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.get.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.search_jobs("Lieferant")
            assert result["total"] == 1

    async def test_export_datev(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"exported": 5, "month": "2024-01"}
        mock_response.raise_for_status.return_value = None

        with patch.object(client, "_get_client") as mock_get:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get.return_value = mock_http

            result = await client.export_datev("2024-01")
            assert result["exported"] == 5

    async def test_login_with_credentials(self):
        client = DocFlowClient(
            base_url="http://test:8000",
            username="admin",
            password="secret",
        )
        login_response = MagicMock()
        login_response.json.return_value = {"access_token": "new-jwt"}
        login_response.raise_for_status.return_value = None

        mock_http = AsyncMock()
        mock_http.post.return_value = login_response

        with patch("httpx.AsyncClient", return_value=mock_http):
            await client._login()
            assert client._token == "new-jwt"

    async def test_headers_with_token(self):
        client = DocFlowClient(token="my-token")
        headers = client._headers()
        assert headers == {"Authorization": "Bearer my-token"}

    async def test_headers_without_token(self):
        client = DocFlowClient(base_url="http://test:8000")
        client._token = ""
        headers = client._headers()
        assert headers == {}


# ── Server Tool Tests ───────────────────────────────────────


class TestDocFlowServerTools:
    """Test MCP server tools return valid JSON strings."""

    @patch("docflow.server._get_client")
    async def test_docflow_health_tool(self, mock_get):
        from docflow.server import docflow_health

        mock_client = AsyncMock()
        mock_client.health.return_value = {"status": "ok"}
        mock_get.return_value = mock_client

        result = await docflow_health()
        data = json.loads(result)
        assert data["status"] == "ok"

    @patch("docflow.server._get_client")
    async def test_docflow_list_jobs_tool(self, mock_get):
        from docflow.server import docflow_list_jobs

        mock_client = AsyncMock()
        mock_client.list_jobs.return_value = SAMPLE_JOBS_LIST
        mock_get.return_value = mock_client

        result = await docflow_list_jobs(status="approved")
        data = json.loads(result)
        assert data["total"] == 1

    @patch("docflow.server._get_client")
    async def test_docflow_get_job_tool(self, mock_get):
        from docflow.server import docflow_get_job

        mock_client = AsyncMock()
        mock_client.get_job.return_value = SAMPLE_JOB
        mock_get.return_value = mock_client

        result = await docflow_get_job(job_id=42)
        data = json.loads(result)
        assert data["id"] == 42
        assert data["document_data"]["invoice_number"] == "RE-2024-001"

    @patch("docflow.server._get_client")
    async def test_docflow_get_bookings_tool(self, mock_get):
        from docflow.server import docflow_get_bookings

        mock_client = AsyncMock()
        mock_client.get_bookings.return_value = SAMPLE_BOOKINGS
        mock_get.return_value = mock_client

        result = await docflow_get_bookings(job_id=42)
        data = json.loads(result)
        assert len(data) == 2
