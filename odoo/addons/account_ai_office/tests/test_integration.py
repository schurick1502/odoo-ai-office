import json
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


class TestKontierungIntegration(TransactionCase):
    """Test the full kontierung workflow: orchestrate → approve → post → move."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")
        cls.env.user.groups_id = [(4, cls.approver_group.id)]

        # Ensure purchase journal exists
        cls.journal = cls.env["account.journal"].search([
            ("type", "=", "purchase"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create({
                "name": "Purchase Journal (Test)",
                "type": "purchase",
                "code": "TPUR",
                "company_id": cls.env.company.id,
            })

        # Ensure required accounts exist
        cls.expense_account = cls.env["account.account"].search([
            ("code", "=", "6300"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.expense_account:
            cls.expense_account = cls.env["account.account"].create({
                "code": "6300",
                "name": "Sonstige betriebliche Aufwendungen",
                "company_id": cls.env.company.id,
                "account_type": "expense",
            })

        cls.tax_account = cls.env["account.account"].search([
            ("code", "=", "1576"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.tax_account:
            cls.tax_account = cls.env["account.account"].create({
                "code": "1576",
                "name": "Abziehbare Vorsteuer 19%",
                "company_id": cls.env.company.id,
                "account_type": "asset_current",
            })

        cls.liabilities_account = cls.env["account.account"].search([
            ("code", "=", "1600"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.liabilities_account:
            cls.liabilities_account = cls.env["account.account"].create({
                "code": "1600",
                "name": "Verbindlichkeiten aus L.u.L.",
                "company_id": cls.env.company.id,
                "account_type": "liability_current",
            })

    def _create_case_with_suggestion(self):
        """Create a case with a ready-to-post accounting_entry suggestion."""
        case = self.env["account.ai.case"].create({
            "name": "KONT-001",
            "period": "2024-01",
        })
        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "accounting_entry",
            "payload_json": json.dumps({
                "lines": [
                    {"account": "6300", "debit": 100.0, "credit": 0.0, "description": "Aufwand"},
                    {"account": "1576", "debit": 19.0, "credit": 0.0, "description": "Vorsteuer 19%"},
                    {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "Verbindlichkeiten"},
                ],
                "amount": 119.0,
                "net_amount": 100.0,
                "tax_amount": 19.0,
                "tax_rate": 0.19,
                "expense_account": "6300",
                "skr_chart": "SKR03",
                "policy_matched": False,
            }),
            "confidence": 0.75,
            "risk_score": 0.15,
            "explanation_md": "Test kontierung",
            "requires_human": True,
            "agent_name": "kontierung_agent",
            "request_id": "test-req-001",
        })
        return case

    def test_post_creates_move(self):
        """action_post creates an account.move from the suggestion."""
        case = self._create_case_with_suggestion()
        case.state = "approved"
        case.action_post()

        self.assertEqual(case.state, "posted")
        self.assertTrue(case.move_id)
        self.assertEqual(case.move_id.ref, "KONT-001")

    def test_move_has_correct_lines(self):
        """Created move has 3 lines with correct debit/credit."""
        case = self._create_case_with_suggestion()
        case.state = "approved"
        case.action_post()

        move = case.move_id
        self.assertEqual(len(move.line_ids), 3)

        expense_line = move.line_ids.filtered(lambda l: l.account_id == self.expense_account)
        self.assertEqual(len(expense_line), 1)
        self.assertAlmostEqual(expense_line.debit, 100.0)

        tax_line = move.line_ids.filtered(lambda l: l.account_id == self.tax_account)
        self.assertEqual(len(tax_line), 1)
        self.assertAlmostEqual(tax_line.debit, 19.0)

        liabilities_line = move.line_ids.filtered(lambda l: l.account_id == self.liabilities_account)
        self.assertEqual(len(liabilities_line), 1)
        self.assertAlmostEqual(liabilities_line.credit, 119.0)

    def test_post_audit_log_has_move_id(self):
        """Audit log from post contains the move_id."""
        case = self._create_case_with_suggestion()
        case.state = "approved"
        case.action_post()

        post_log = case.audit_log_ids.filtered(lambda rec: rec.action == "post")
        self.assertEqual(len(post_log), 1)
        after = json.loads(post_log.after_json)
        self.assertEqual(after["move_id"], case.move_id.id)

    def test_post_without_suggestion_raises(self):
        """action_post raises UserError if no accounting_entry suggestion exists."""
        case = self.env["account.ai.case"].create({
            "name": "KONT-EMPTY",
            "period": "2024-01",
        })
        case.state = "approved"
        with self.assertRaises(UserError):
            case.action_post()

    def test_post_with_missing_account_raises(self):
        """action_post raises UserError if an account code cannot be resolved."""
        case = self.env["account.ai.case"].create({
            "name": "KONT-BAD",
            "period": "2024-01",
        })
        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "accounting_entry",
            "payload_json": json.dumps({
                "lines": [
                    {"account": "9999", "debit": 100.0, "credit": 0.0, "description": "Unknown"},
                ],
            }),
            "confidence": 0.5,
            "risk_score": 0.5,
            "requires_human": True,
            "agent_name": "test",
            "request_id": "test-bad",
        })
        case.state = "approved"
        with self.assertRaises(UserError):
            case.action_post()

    def test_orchestrate_sends_policies(self):
        """action_run_orchestrator includes policies in the context."""
        case = self.env["account.ai.case"].create({
            "name": "KONT-POL",
            "period": "2024-01",
        })

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "case_id": case.id,
            "request_id": "test-pol",
            "suggestions": [],
            "status": "ok",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp) as mock_post:
            case.action_run_orchestrator()

        call_args = mock_post.call_args
        context = call_args.kwargs.get("json", call_args[1].get("json", {})).get("context", {})
        self.assertIn("policies", context)
        self.assertIsInstance(context["policies"], list)
