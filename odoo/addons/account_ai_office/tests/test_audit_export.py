import base64
import csv
import io
import json

from odoo.tests.common import TransactionCase


class TestAuditLogExport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")
        cls.env.user.groups_id = [(4, cls.approver_group.id)]

    def _create_case_with_logs(self):
        """Create a case and trigger actions to generate audit logs."""
        case = self.env["account.ai.case"].create({
            "name": "EXPORT-001",
            "partner_id": self.env.ref("base.res_partner_1").id,
            "period": "2024-01",
        })
        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "accounting_entry",
            "payload_json": json.dumps({
                "lines": [
                    {"account": "6300", "debit": 119.0, "credit": 0.0, "description": "Aufwand"},
                    {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "Verb."},
                ],
            }),
            "confidence": 0.9,
            "risk_score": 0.1,
            "requires_human": True,
            "agent_name": "test",
            "request_id": "test-export",
        })
        case.action_propose()
        return case

    def test_export_csv_produces_file(self):
        """Export wizard generates a CSV file with correct columns."""
        self._create_case_with_logs()
        wizard = self.env["account.ai.audit_log.export"].create({
            "date_from": "2020-01-01",
            "date_to": "2030-12-31",
            "export_format": "csv",
        })
        wizard.action_export()
        self.assertTrue(wizard.file_data)
        self.assertTrue(wizard.file_name.endswith(".csv"))

        content = base64.b64decode(wizard.file_data).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        self.assertGreater(len(rows), 0)
        expected_cols = {"date", "case_ref", "actor_type", "actor", "action", "before_json", "after_json"}
        self.assertEqual(set(reader.fieldnames), expected_cols)

    def test_export_json_produces_file(self):
        """Export wizard generates a JSON file with correct structure."""
        self._create_case_with_logs()
        wizard = self.env["account.ai.audit_log.export"].create({
            "date_from": "2020-01-01",
            "date_to": "2030-12-31",
            "export_format": "json",
        })
        wizard.action_export()
        self.assertTrue(wizard.file_data)
        self.assertTrue(wizard.file_name.endswith(".json"))

        content = base64.b64decode(wizard.file_data).decode("utf-8")
        data = json.loads(content)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn("case_ref", data[0])
        self.assertIn("action", data[0])

    def test_export_date_filter(self):
        """Export wizard respects date range filter."""
        self._create_case_with_logs()
        wizard = self.env["account.ai.audit_log.export"].create({
            "date_from": "2099-01-01",
            "date_to": "2099-12-31",
            "export_format": "csv",
        })
        wizard.action_export()
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        self.assertEqual(len(rows), 0)

    def test_export_empty_result_still_has_header(self):
        """CSV export with no matching logs still has the header row."""
        wizard = self.env["account.ai.audit_log.export"].create({
            "date_from": "2099-01-01",
            "date_to": "2099-12-31",
            "export_format": "csv",
        })
        wizard.action_export()
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        self.assertIn("date,case_ref,actor_type,actor,action,before_json,after_json", content)
