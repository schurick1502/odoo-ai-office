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

        orchestrate_logs = case.audit_log_ids.filtered(lambda l: l.action == "orchestrate")
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
