"""Tests for the Odoo AI Office MCP server and client."""

import json
from unittest.mock import MagicMock, patch

import pytest

from mcp_servers.odoo_bridge.client import OdooAiOfficeClient


# ── Client Tests ────────────────────────────────────────────


class TestOdooClient:
    """Test OdooAiOfficeClient with mocked XML-RPC."""

    @pytest.fixture
    def client(self):
        c = OdooAiOfficeClient(
            url="http://test:8069",
            db="test_db",
            username="admin",
            password="admin",
        )
        c._uid = 2  # Skip real auth
        c._common = MagicMock()
        c._object = MagicMock()
        return c

    def test_authenticate(self):
        c = OdooAiOfficeClient(url="http://test:8069", db="test", username="admin", password="pw")
        mock_common = MagicMock()
        mock_common.authenticate.return_value = 5
        c._common = mock_common

        uid = c.authenticate()
        assert uid == 5
        mock_common.authenticate.assert_called_once_with("test", "admin", "pw", {})

    def test_authenticate_failure(self):
        c = OdooAiOfficeClient(url="http://test:8069", db="test", username="admin", password="bad")
        mock_common = MagicMock()
        mock_common.authenticate.return_value = False
        c._common = mock_common

        with pytest.raises(ConnectionError, match="authentication failed"):
            c.authenticate()

    def test_list_cases(self, client):
        client._object.execute_kw.return_value = [
            {"id": 1, "name": "AIC-2024-00001", "state": "new"},
            {"id": 2, "name": "AIC-2024-00002", "state": "proposed"},
        ]
        result = client.list_cases(state="new")
        assert len(result) == 2
        client._object.execute_kw.assert_called_once()

    def test_list_cases_no_filter(self, client):
        client._object.execute_kw.return_value = []
        result = client.list_cases()
        assert result == []
        call_args = client._object.execute_kw.call_args
        assert call_args[0][4] == "search_read"
        assert call_args[0][5] == [[]]

    def test_get_case(self, client):
        client._object.execute_kw.return_value = [
            {"id": 42, "name": "AIC-2024-00042", "state": "proposed", "partner_id": [7, "Test GmbH"]},
        ]
        result = client.get_case(42)
        assert result["name"] == "AIC-2024-00042"

    def test_get_case_not_found(self, client):
        client._object.execute_kw.return_value = []
        with pytest.raises(ValueError, match="not found"):
            client.get_case(999)

    def test_create_case_with_partner_name(self, client):
        # First call: search_read for partner → not found
        # Second call: create partner → id 10
        # Third call: create case → id 42
        client._object.execute_kw.side_effect = [
            [],   # search_read partner by name
            10,   # create partner
            42,   # create case
        ]
        case_id = client.create_case({
            "partner_name": "Neue Firma GmbH",
            "period": "2024-01",
            "source_model": "docflow.job",
            "source_id": 7,
        })
        assert case_id == 42

    def test_create_case_existing_partner(self, client):
        client._object.execute_kw.side_effect = [
            [{"id": 5}],  # search_read partner → found
            42,            # create case
        ]
        case_id = client.create_case({
            "partner_name": "Existing GmbH",
            "period": "2024-01",
        })
        assert case_id == 42

    def test_add_suggestion(self, client):
        client._object.execute_kw.return_value = 99
        suggestion_id = client.add_suggestion(42, {
            "suggestion_type": "accounting_entry",
            "payload": {"lines": [{"account": "6300", "debit": 100, "credit": 0, "description": "Test"}]},
            "confidence": 0.9,
            "risk_score": 0.1,
            "explanation": "Test suggestion",
            "agent_name": "docflow_bridge",
        })
        assert suggestion_id == 99
        call_args = client._object.execute_kw.call_args
        create_vals = call_args[0][5][0]
        assert create_vals["case_id"] == 42
        assert create_vals["confidence"] == 0.9
        assert '"lines"' in create_vals["payload_json"]

    def test_action_propose(self, client):
        client._object.execute_kw.return_value = True
        result = client.action_propose(42)
        assert result is True

    def test_action_approve(self, client):
        client._object.execute_kw.return_value = True
        result = client.action_approve(42)
        assert result is True

    def test_action_post(self, client):
        client._object.execute_kw.return_value = True
        result = client.action_post(42)
        assert result is True

    def test_action_export(self, client):
        client._object.execute_kw.return_value = True
        result = client.action_export(42)
        assert result is True

    def test_get_suggestions(self, client):
        client._object.execute_kw.return_value = [
            {"id": 1, "suggestion_type": "enrichment", "confidence": 0.8},
            {"id": 2, "suggestion_type": "accounting_entry", "confidence": 0.92},
        ]
        result = client.get_suggestions(42)
        assert len(result) == 2

    def test_search_partners(self, client):
        client._object.execute_kw.return_value = [
            {"id": 5, "name": "Test GmbH", "email": "test@example.com"},
        ]
        result = client.search_partners("Test")
        assert len(result) == 1
        assert result[0]["name"] == "Test GmbH"

    def test_list_audit_logs(self, client):
        client._object.execute_kw.return_value = [
            {"id": 1, "action": "email_intake", "actor": "mail_intake"},
            {"id": 2, "action": "approve", "actor": "admin"},
        ]
        result = client.list_audit_logs(42)
        assert len(result) == 2

    def test_health_ok(self):
        c = OdooAiOfficeClient(url="http://test:8069", db="test", username="admin", password="pw")
        mock_common = MagicMock()
        mock_common.version.return_value = {"server_version": "18.0"}
        mock_common.authenticate.return_value = 2
        c._common = mock_common

        result = c.health()
        assert result["status"] == "ok"
        assert result["odoo_version"] == "18.0"

    def test_health_error(self):
        c = OdooAiOfficeClient(url="http://test:8069", db="test", username="admin", password="bad")
        mock_common = MagicMock()
        mock_common.version.side_effect = ConnectionRefusedError("refused")
        c._common = mock_common

        result = c.health()
        assert result["status"] == "error"

    def test_case_exists_true(self, client):
        client._object.execute_kw.return_value = [{"id": 42}]
        assert client.case_exists("docflow.job", 7) is True

    def test_case_exists_false(self, client):
        client._object.execute_kw.return_value = []
        assert client.case_exists("docflow.job", 999) is False


# ── Server Tool Tests ───────────────────────────────────────


class TestOdooServerTools:
    """Test MCP server tools return valid JSON strings."""

    @patch("mcp_servers.odoo_bridge.server._get_client")
    def test_odoo_health_tool(self, mock_get):
        from mcp_servers.odoo_bridge.server import odoo_health

        mock_client = MagicMock()
        mock_client.health.return_value = {"status": "ok", "odoo_version": "18.0"}
        mock_get.return_value = mock_client

        result = odoo_health()
        data = json.loads(result)
        assert data["status"] == "ok"

    @patch("mcp_servers.odoo_bridge.server._get_client")
    def test_odoo_list_cases_tool(self, mock_get):
        from mcp_servers.odoo_bridge.server import odoo_list_cases

        mock_client = MagicMock()
        mock_client.list_cases.return_value = [
            {"id": 1, "name": "AIC-2024-00001", "state": "new"},
        ]
        mock_get.return_value = mock_client

        result = odoo_list_cases(state="new")
        data = json.loads(result)
        assert len(data) == 1

    @patch("mcp_servers.odoo_bridge.server._get_client")
    def test_odoo_create_case_tool(self, mock_get):
        from mcp_servers.odoo_bridge.server import odoo_create_case

        mock_client = MagicMock()
        mock_client.create_case.return_value = 42
        mock_get.return_value = mock_client

        result = odoo_create_case(
            partner_name="Test GmbH",
            period="2024-01",
            source_model="docflow.job",
            source_id=7,
        )
        data = json.loads(result)
        assert data["case_id"] == 42
        assert data["status"] == "created"

    @patch("mcp_servers.odoo_bridge.server._get_client")
    def test_odoo_add_suggestion_tool(self, mock_get):
        from mcp_servers.odoo_bridge.server import odoo_add_suggestion

        mock_client = MagicMock()
        mock_client.add_suggestion.return_value = 99
        mock_get.return_value = mock_client

        result = odoo_add_suggestion(
            case_id=42,
            suggestion_type="accounting_entry",
            payload='{"lines": []}',
            confidence=0.9,
            risk_score=0.1,
            explanation="Test",
            agent_name="test_agent",
        )
        data = json.loads(result)
        assert data["suggestion_id"] == 99

    @patch("mcp_servers.odoo_bridge.server._get_client")
    def test_odoo_propose_case_tool(self, mock_get):
        from mcp_servers.odoo_bridge.server import odoo_propose_case

        mock_client = MagicMock()
        mock_get.return_value = mock_client

        result = odoo_propose_case(case_id=42)
        data = json.loads(result)
        assert data["state"] == "proposed"
