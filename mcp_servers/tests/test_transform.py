"""Tests for bridge transform functions."""

import pytest

from mcp_servers.bridge.transform import (
    calculate_risk,
    transform_bookings_to_suggestion,
    transform_enrichment_suggestions,
    transform_job_to_case_vals,
)
from mcp_servers.tests.conftest import SAMPLE_BOOKINGS, SAMPLE_JOB


class TestTransformJobToCaseVals:
    """Test transform_job_to_case_vals()."""

    def test_full_job(self):
        vals = transform_job_to_case_vals(SAMPLE_JOB)
        assert vals["partner_name"] == "Test Lieferant GmbH"
        assert vals["period"] == "2024-01"
        assert vals["source_model"] == "docflow.job"
        assert vals["source_id"] == 42

    def test_missing_document_data(self):
        job = {"id": 99, "status": "approved"}
        vals = transform_job_to_case_vals(job)
        assert vals["partner_name"] == ""
        assert vals["period"] == ""
        assert vals["source_id"] == 99

    def test_null_document_data(self):
        job = {"id": 1, "document_data": None}
        vals = transform_job_to_case_vals(job)
        assert vals["partner_name"] == ""

    def test_period_extraction(self):
        job = {"id": 1, "document_data": {"date_document": "2025-03-15"}}
        vals = transform_job_to_case_vals(job)
        assert vals["period"] == "2025-03"

    def test_period_extraction_short_month(self):
        job = {"id": 1, "document_data": {"date_document": "2025-1-05"}}
        vals = transform_job_to_case_vals(job)
        assert vals["period"] == "2025-01"


class TestTransformEnrichmentSuggestions:
    """Test transform_enrichment_suggestions()."""

    def test_full_job_extracts_all_fields(self):
        suggestions = transform_enrichment_suggestions(SAMPLE_JOB)
        fields = {s["payload"]["field"] for s in suggestions}
        assert "invoice_number" in fields
        assert "invoice_date" in fields
        assert "partner_name" in fields
        assert "amount_total" in fields
        assert "amount_net" in fields
        assert "tax_amount" in fields

    def test_enrichment_values(self):
        suggestions = transform_enrichment_suggestions(SAMPLE_JOB)
        by_field = {s["payload"]["field"]: s for s in suggestions}
        assert by_field["invoice_number"]["payload"]["value"] == "RE-2024-001"
        assert by_field["invoice_date"]["payload"]["value"] == "2024-01-15"
        assert by_field["amount_total"]["payload"]["value"] == "119.0"

    def test_enrichment_metadata(self):
        suggestions = transform_enrichment_suggestions(SAMPLE_JOB)
        for sugg in suggestions:
            assert sugg["suggestion_type"] == "enrichment"
            assert sugg["agent_name"] == "docflow_bridge"
            assert sugg["confidence"] == 0.92
            assert sugg["risk_score"] == 0.0

    def test_empty_document_data(self):
        job = {"id": 1, "document_data": None}
        suggestions = transform_enrichment_suggestions(job)
        assert suggestions == []

    def test_skips_empty_values(self):
        job = {"id": 1, "document_data": {"sender_name": "", "invoice_number": None}}
        suggestions = transform_enrichment_suggestions(job)
        assert len(suggestions) == 0

    def test_zero_values_included(self):
        job = {"id": 1, "document_data": {"total_gross": 0}}
        suggestions = transform_enrichment_suggestions(job)
        fields = {s["payload"]["field"] for s in suggestions}
        # 0 is not None/"", so it should be included
        assert "amount_total" in fields


class TestTransformBookingsToSuggestion:
    """Test transform_bookings_to_suggestion()."""

    def test_with_bookings(self):
        sugg = transform_bookings_to_suggestion(SAMPLE_JOB, SAMPLE_BOOKINGS)
        assert sugg["suggestion_type"] == "accounting_entry"
        assert sugg["agent_name"] == "docflow_bridge"
        lines = sugg["payload"]["lines"]
        # 2 bookings × 2 sides (debit + credit) = 4 lines
        assert len(lines) == 4
        # Check debit lines
        debit_lines = [rec for rec in lines if rec["debit"] > 0]
        assert len(debit_lines) == 2
        assert debit_lines[0]["account"] == "6300"
        assert debit_lines[0]["debit"] == 100.00
        assert debit_lines[1]["account"] == "1576"
        assert debit_lines[1]["debit"] == 19.00

    def test_with_bookings_balanced(self):
        sugg = transform_bookings_to_suggestion(SAMPLE_JOB, SAMPLE_BOOKINGS)
        lines = sugg["payload"]["lines"]
        total_debit = sum(rec["debit"] for rec in lines)
        total_credit = sum(rec["credit"] for rec in lines)
        assert abs(total_debit - total_credit) < 0.01

    def test_without_bookings_uses_acct_suggestion(self):
        sugg = transform_bookings_to_suggestion(SAMPLE_JOB, [])
        lines = sugg["payload"]["lines"]
        assert len(lines) == 3  # expense + vorsteuer + verbindlichkeiten
        assert lines[0]["account"] == "6300"
        assert lines[0]["debit"] == 100.00
        assert lines[1]["account"] == "1576"
        assert lines[1]["debit"] == 19.00
        assert lines[2]["account"] == "1600"
        assert lines[2]["credit"] == 119.00

    def test_without_bookings_balanced(self):
        sugg = transform_bookings_to_suggestion(SAMPLE_JOB, [])
        lines = sugg["payload"]["lines"]
        total_debit = sum(rec["debit"] for rec in lines)
        total_credit = sum(rec["credit"] for rec in lines)
        assert abs(total_debit - total_credit) < 0.01

    def test_payload_metadata(self):
        sugg = transform_bookings_to_suggestion(SAMPLE_JOB, SAMPLE_BOOKINGS)
        payload = sugg["payload"]
        assert payload["amount"] == 119.00
        assert payload["net_amount"] == 100.00
        assert payload["tax_amount"] == 19.00
        assert payload["tax_rate"] == 0.19
        assert payload["skr_chart"] == "SKR03"
        assert payload["source"] == "documentflow"
        assert payload["docflow_job_id"] == 42

    def test_confidence_from_acct_suggestion(self):
        sugg = transform_bookings_to_suggestion(SAMPLE_JOB, [])
        assert sugg["confidence"] == 0.88  # From accounting_suggestion.confidence

    def test_no_data_returns_empty_lines(self):
        job = {"id": 1, "document_data": {"total_gross": 0}}
        sugg = transform_bookings_to_suggestion(job, [])
        assert sugg["payload"]["lines"] == []

    def test_7_percent_tax(self):
        job = {
            "id": 2,
            "document_data": {
                "total_gross": 107.00,
                "total_net": 100.00,
                "vat_amount": 7.00,
                "vat_rate": 0.07,
                "confidence": 0.85,
                "accounting_suggestion": {
                    "booking_account": "4930",
                    "counter_account": "1600",
                    "tax_key": "7",
                    "confidence": 0.85,
                },
            },
        }
        sugg = transform_bookings_to_suggestion(job, [])
        lines = sugg["payload"]["lines"]
        assert lines[1]["account"] == "1571"  # Vorsteuer 7%
        assert sugg["payload"]["tax_rate"] == 0.07


class TestCalculateRisk:
    """Test calculate_risk()."""

    def test_high_confidence_low_risk(self):
        risk = calculate_risk({"confidence": 0.95, "sender_name": "X", "invoice_number": "1", "total_gross": 100})
        assert risk == 0.05

    def test_low_confidence_high_risk(self):
        risk = calculate_risk({"confidence": 0.3, "sender_name": "X", "invoice_number": "1", "total_gross": 100})
        assert risk == 0.7

    def test_missing_sender_adds_penalty(self):
        risk_with = calculate_risk({"confidence": 0.9, "sender_name": "X", "invoice_number": "1", "total_gross": 100})
        risk_without = calculate_risk({"confidence": 0.9, "invoice_number": "1", "total_gross": 100})
        assert risk_without > risk_with

    def test_missing_invoice_number_adds_penalty(self):
        risk_with = calculate_risk({"confidence": 0.9, "sender_name": "X", "invoice_number": "1", "total_gross": 100})
        risk_without = calculate_risk({"confidence": 0.9, "sender_name": "X", "total_gross": 100})
        assert risk_without > risk_with

    def test_zero_amount_adds_penalty(self):
        risk_with = calculate_risk({"confidence": 0.9, "sender_name": "X", "invoice_number": "1", "total_gross": 100})
        risk_without = calculate_risk({"confidence": 0.9, "sender_name": "X", "invoice_number": "1", "total_gross": 0})
        assert risk_without > risk_with

    def test_max_risk_capped_at_one(self):
        risk = calculate_risk({"confidence": 0.0})
        assert risk <= 1.0

    def test_all_penalties(self):
        risk = calculate_risk({"confidence": 0.5})
        # 0.5 base + 0.1 (no sender) + 0.05 (no invoice) + 0.1 (no amount) = 0.75
        assert risk == 0.75
