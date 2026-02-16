"""Tests for bridge sync logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bridge.config import BridgeConfig
from bridge.sync import BridgeSync
from tests.conftest import SAMPLE_BOOKINGS, SAMPLE_JOB, SAMPLE_JOBS_LIST


@pytest.fixture
def config():
    return BridgeConfig(
        docflow_url="http://test:8000",
        docflow_token="test-token",
        odoo_url="http://test:8069",
        odoo_db="test",
        odoo_username="admin",
        odoo_password="admin",
        sync_statuses=["approved"],
        dry_run=False,
    )


@pytest.fixture
def bridge(config):
    b = BridgeSync(config)
    b.docflow = AsyncMock()
    b.odoo = MagicMock()
    return b


class TestBridgeSync:
    """Test BridgeSync sync_once() logic."""

    async def test_sync_once_creates_case(self, bridge):
        bridge.docflow.list_jobs.return_value = SAMPLE_JOBS_LIST
        bridge.docflow.get_job.return_value = SAMPLE_JOB
        bridge.docflow.get_bookings.return_value = SAMPLE_BOOKINGS
        bridge.odoo.case_exists.return_value = False
        bridge.odoo.create_case.return_value = 42
        bridge.odoo.add_suggestion.return_value = 1
        bridge.odoo.action_propose.return_value = True

        stats = await bridge.sync_once()
        assert stats["created"] == 1
        assert stats["skipped"] == 0
        assert stats["errors"] == []

        # Verify case was created
        bridge.odoo.create_case.assert_called_once()
        case_vals = bridge.odoo.create_case.call_args[0][0]
        assert case_vals["partner_name"] == "Test Lieferant GmbH"
        assert case_vals["source_model"] == "docflow.job"
        assert case_vals["source_id"] == 42

    async def test_sync_once_skips_existing(self, bridge):
        bridge.docflow.list_jobs.return_value = SAMPLE_JOBS_LIST
        bridge.odoo.case_exists.return_value = True

        stats = await bridge.sync_once()
        assert stats["created"] == 0
        assert stats["skipped"] == 1

        # Case should not be created
        bridge.odoo.create_case.assert_not_called()

    async def test_sync_once_adds_suggestions(self, bridge):
        bridge.docflow.list_jobs.return_value = SAMPLE_JOBS_LIST
        bridge.docflow.get_job.return_value = SAMPLE_JOB
        bridge.docflow.get_bookings.return_value = SAMPLE_BOOKINGS
        bridge.odoo.case_exists.return_value = False
        bridge.odoo.create_case.return_value = 42
        bridge.odoo.add_suggestion.return_value = 1
        bridge.odoo.action_propose.return_value = True

        await bridge.sync_once()

        # Should have: 6 enrichment + 1 accounting_entry = 7 suggestions
        assert bridge.odoo.add_suggestion.call_count >= 2

        # Check types of suggestions added
        calls = bridge.odoo.add_suggestion.call_args_list
        types = {call[0][1]["suggestion_type"] for call in calls}
        assert "enrichment" in types
        assert "accounting_entry" in types

    async def test_sync_once_proposes_case(self, bridge):
        bridge.docflow.list_jobs.return_value = SAMPLE_JOBS_LIST
        bridge.docflow.get_job.return_value = SAMPLE_JOB
        bridge.docflow.get_bookings.return_value = SAMPLE_BOOKINGS
        bridge.odoo.case_exists.return_value = False
        bridge.odoo.create_case.return_value = 42
        bridge.odoo.add_suggestion.return_value = 1
        bridge.odoo.action_propose.return_value = True

        await bridge.sync_once()
        bridge.odoo.action_propose.assert_called_once_with(42)

    async def test_sync_once_handles_errors(self, bridge):
        bridge.docflow.list_jobs.return_value = SAMPLE_JOBS_LIST
        bridge.docflow.get_job.side_effect = Exception("Connection lost")
        bridge.odoo.case_exists.return_value = False

        stats = await bridge.sync_once()
        assert stats["created"] == 0
        assert len(stats["errors"]) == 1
        assert "Connection lost" in stats["errors"][0]["error"]

    async def test_sync_once_handles_docflow_error(self, bridge):
        bridge.docflow.list_jobs.side_effect = Exception("DocFlow down")

        stats = await bridge.sync_once()
        assert stats["created"] == 0
        assert len(stats["errors"]) == 1

    async def test_sync_once_dry_run(self, bridge):
        bridge.config.dry_run = True
        bridge.docflow.list_jobs.return_value = SAMPLE_JOBS_LIST
        bridge.docflow.get_job.return_value = SAMPLE_JOB
        bridge.docflow.get_bookings.return_value = SAMPLE_BOOKINGS
        bridge.odoo.case_exists.return_value = False

        stats = await bridge.sync_once()
        assert stats["created"] == 1

        # In dry run, no actual Odoo writes
        bridge.odoo.create_case.assert_not_called()
        bridge.odoo.add_suggestion.assert_not_called()

    async def test_sync_once_empty_job_list(self, bridge):
        bridge.docflow.list_jobs.return_value = {"items": [], "total": 0}

        stats = await bridge.sync_once()
        assert stats["created"] == 0
        assert stats["skipped"] == 0
        assert stats["errors"] == []

    async def test_sync_multiple_statuses(self, bridge):
        bridge.config.sync_statuses = ["approved", "exported"]
        bridge.docflow.list_jobs.return_value = {"items": [], "total": 0}

        await bridge.sync_once()
        assert bridge.docflow.list_jobs.call_count == 2


class TestBridgeConfig:
    """Test BridgeConfig."""

    def test_from_env_defaults(self):
        config = BridgeConfig.from_env()
        assert config.docflow_url == "http://localhost:8000"
        assert config.odoo_url == "http://localhost:8069"
        assert config.sync_interval == 60
        assert config.sync_statuses == ["approved"]
        assert config.dry_run is False

    @patch.dict("os.environ", {
        "DOCFLOW_URL": "http://custom:9000",
        "BRIDGE_SYNC_STATUSES": "approved,exported",
        "BRIDGE_DRY_RUN": "true",
    })
    def test_from_env_custom(self):
        config = BridgeConfig.from_env()
        assert config.docflow_url == "http://custom:9000"
        assert config.sync_statuses == ["approved", "exported"]
        assert config.dry_run is True
