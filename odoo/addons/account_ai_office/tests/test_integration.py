from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestIntegration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")
        cls.env.user.groups_id = [(4, cls.approver_group.id)]

    def _create_case(self):
        return self.env["account.ai.case"].create({
            "name": "INT-001",
            "period": "2024-01",
        })

    def _mock_response(self, case_id):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "case_id": case_id,
            "request_id": "test-req-001",
            "suggestions": [{
                "suggestion_type": "accounting_entry",
                "payload": {
                    "lines": [
                        {"account": "4400", "debit": 100.0, "credit": 0.0},
                        {"account": "1200", "debit": 0.0, "credit": 100.0},
                    ],
                },
                "confidence": 0.9,
                "risk_score": 0.1,
                "explanation": "Test suggestion",
                "requires_human": True,
                "agent_name": "test_agent",
            }],
            "status": "ok",
        }
        mock.raise_for_status = MagicMock()
        return mock

    def test_run_orchestrator_creates_suggestions(self):
        """action_run_orchestrator creates suggestions from service response."""
        case = self._create_case()
        mock_resp = self._mock_response(case.id)

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_run_orchestrator()

        self.assertEqual(case.state, "proposed")
        self.assertEqual(len(case.suggestion_ids), 1)
        self.assertEqual(case.suggestion_ids[0].agent_name, "test_agent")
        self.assertAlmostEqual(case.suggestion_ids[0].confidence, 0.9)

    def test_run_orchestrator_writes_audit_log(self):
        """action_run_orchestrator writes an audit log entry."""
        case = self._create_case()
        mock_resp = self._mock_response(case.id)

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_run_orchestrator()

        orchestrate_logs = case.audit_log_ids.filtered(lambda rec: rec.action == "orchestrate")
        self.assertEqual(len(orchestrate_logs), 1)

    def test_run_orchestrator_connection_error(self):
        """action_run_orchestrator raises UserError on connection failure."""
        case = self._create_case()
        import requests as req_lib

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", side_effect=req_lib.exceptions.ConnectionError):
            with self.assertRaises(UserError):
                case.action_run_orchestrator()

        self.assertEqual(case.state, "new")

    def test_run_orchestrator_only_from_new_enriched(self):
        """action_run_orchestrator raises UserError from non-new/enriched states."""
        case = self._create_case()
        mock_resp = self._mock_response(case.id)

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_run_orchestrator()

        self.assertEqual(case.state, "proposed")
        with self.assertRaises(UserError):
            case.action_run_orchestrator()

    def test_run_orchestrator_from_enriched(self):
        """action_run_orchestrator works from 'enriched' state."""
        case = self._create_case()
        case.state = "enriched"
        mock_resp = self._mock_response(case.id)

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_run_orchestrator()

        self.assertEqual(case.state, "proposed")


class TestEnrichIntegration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_group = cls.env.ref("account_ai_office.ai_office_user")
        cls.env.user.groups_id = [(4, cls.user_group.id)]

    def _create_case_with_doc(self):
        import base64
        case = self.env["account.ai.case"].create({
            "name": "ENRICH-001",
            "period": "2024-01",
        })
        attachment = self.env["ir.attachment"].create({
            "name": "RE-2024-00123_119.00.pdf",
            "mimetype": "application/pdf",
            "datas": base64.b64encode(b"fake pdf content"),
        })
        case.document_ids = [(6, 0, [attachment.id])]
        return case

    def _mock_enrich_response(self, case_id):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "case_id": case_id,
            "request_id": "enrich-test-001",
            "suggestions": [
                {
                    "field": "invoice_date",
                    "value": "2024-01-23",
                    "confidence": 0.6,
                    "source": "filename_parser",
                },
                {
                    "field": "invoice_number",
                    "value": "RE-00123",
                    "confidence": 0.7,
                    "source": "filename_parser",
                },
            ],
            "status": "ok",
        }
        mock.raise_for_status = MagicMock()
        return mock

    def test_action_enrich_creates_suggestions(self):
        """action_enrich creates enrichment suggestions."""
        case = self._create_case_with_doc()
        mock_resp = self._mock_enrich_response(case.id)

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_enrich()

        self.assertEqual(case.state, "enriched")
        enrichment_suggestions = case.suggestion_ids.filtered(
            lambda s: s.suggestion_type == "enrichment"
        )
        self.assertEqual(len(enrichment_suggestions), 2)

    def test_action_enrich_writes_audit_log(self):
        """action_enrich writes an audit log entry."""
        case = self._create_case_with_doc()
        mock_resp = self._mock_enrich_response(case.id)

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_enrich()

        enrich_logs = case.audit_log_ids.filtered(lambda rec: rec.action == "enrich")
        self.assertEqual(len(enrich_logs), 1)

    def test_action_enrich_only_from_new(self):
        """action_enrich raises UserError from non-new states."""
        case = self._create_case_with_doc()
        case.state = "enriched"
        with self.assertRaises(UserError):
            case.action_enrich()

    def test_action_enrich_connection_error(self):
        """action_enrich raises UserError on connection failure."""
        case = self._create_case_with_doc()
        import requests as req_lib

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", side_effect=req_lib.exceptions.ConnectionError):
            with self.assertRaises(UserError):
                case.action_enrich()

        self.assertEqual(case.state, "new")
