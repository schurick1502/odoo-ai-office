import json
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestOPOS(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")
        cls.env.user.groups_id = [(4, cls.approver_group.id)]

        # Ensure purchase journal
        cls.journal = cls.env["account.journal"].search([
            ("type", "=", "purchase"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create({
                "name": "Purchase Journal (OPOS Test)",
                "type": "purchase",
                "code": "TOPP",
                "company_id": cls.env.company.id,
            })

        # Accounts
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
                "account_type": "liability_payable",
            })

        cls.partner = cls.env.ref("base.res_partner_1")

    def _create_posted_case(self):
        """Create a case, add valid suggestion, approve and post it."""
        case = self.env["account.ai.case"].create({
            "name": "OPOS-001",
            "partner_id": self.partner.id,
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
            }),
            "confidence": 0.9,
            "risk_score": 0.1,
            "requires_human": True,
            "agent_name": "test",
            "request_id": "opos-test",
        })
        case.action_propose()
        case.action_approve()
        case.action_post()
        return case

    def _mock_opos_response(self, case_id, matches=None):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {
            "case_id": case_id,
            "request_id": "opos-test-001",
            "suggestions": [{
                "suggestion_type": "reconciliation",
                "payload": {
                    "matches": matches or [],
                    "unmatched_debit": [],
                    "unmatched_credit": [],
                },
                "confidence": 0.9,
                "risk_score": 0.1,
                "explanation": "Test OPOS result",
                "requires_human": True,
                "agent_name": "opos_agent",
            }],
            "status": "ok",
        }
        mock.raise_for_status = MagicMock()
        return mock

    # ── action_run_opos tests ────────────────────────────────────────

    def test_run_opos_only_from_posted(self):
        """action_run_opos raises UserError if state != posted."""
        case = self.env["account.ai.case"].create({
            "name": "OPOS-NEW",
            "partner_id": self.partner.id,
            "period": "2024-01",
        })
        with self.assertRaises(UserError):
            case.action_run_opos()

    def test_run_opos_requires_move_id(self):
        """action_run_opos raises UserError if no move_id."""
        case = self.env["account.ai.case"].create({
            "name": "OPOS-NOMOVE",
            "partner_id": self.partner.id,
            "period": "2024-01",
        })
        case.state = "posted"
        with self.assertRaises(UserError):
            case.action_run_opos()

    def test_run_opos_creates_reconciliation_suggestion(self):
        """action_run_opos creates reconciliation suggestions from service response."""
        case = self._create_posted_case()
        mock_resp = self._mock_opos_response(case.id, matches=[{
            "debit_line_id": 1, "credit_line_id": 2,
            "amount": 119.0, "match_type": "exact_amount",
            "confidence": 0.8, "reason": "Exact amount match",
        }])
        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_run_opos()

        recon = case.suggestion_ids.filtered(lambda s: s.suggestion_type == "reconciliation")
        self.assertEqual(len(recon), 1)
        self.assertEqual(recon.agent_name, "opos_agent")

    def test_run_opos_writes_audit_log(self):
        """action_run_opos writes an audit log entry."""
        case = self._create_posted_case()
        mock_resp = self._mock_opos_response(case.id)
        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post", return_value=mock_resp):
            case.action_run_opos()

        opos_logs = case.audit_log_ids.filtered(lambda rec: rec.action == "opos_match")
        self.assertEqual(len(opos_logs), 1)

    def test_run_opos_connection_error(self):
        """action_run_opos raises UserError on connection failure."""
        case = self._create_posted_case()
        import requests as req_lib
        with patch("odoo.addons.account_ai_office.models.ai_case.requests.post",
                    side_effect=req_lib.exceptions.ConnectionError):
            with self.assertRaises(UserError):
                case.action_run_opos()

    # ── action_apply_reconciliation tests ─────────────────────────────

    def test_apply_reconciliation_requires_approver(self):
        """action_apply_reconciliation raises UserError for non-approver."""
        case = self.env["account.ai.case"].create({
            "name": "OPOS-NOAPPR",
            "partner_id": self.partner.id,
            "period": "2024-01",
        })
        case.state = "posted"
        user_group = self.env.ref("account_ai_office.ai_office_user")
        self.env.user.groups_id = [(3, self.approver_group.id), (4, user_group.id)]
        with self.assertRaises(UserError):
            case.action_apply_reconciliation()
        # Restore approver group for subsequent tests
        self.env.user.groups_id = [(4, self.approver_group.id)]

    def test_apply_reconciliation_requires_posted(self):
        """action_apply_reconciliation raises UserError if state != posted."""
        case = self.env["account.ai.case"].create({
            "name": "OPOS-NOTPOSTED",
            "partner_id": self.partner.id,
            "period": "2024-01",
        })
        with self.assertRaises(UserError):
            case.action_apply_reconciliation()

    def test_apply_reconciliation_no_suggestions_raises(self):
        """action_apply_reconciliation raises UserError if no reconciliation suggestions."""
        case = self._create_posted_case()
        with self.assertRaises(UserError):
            case.action_apply_reconciliation()

    def test_apply_reconciliation_writes_audit_log(self):
        """action_apply_reconciliation writes an audit log entry."""
        case = self._create_posted_case()
        # Manually create a reconciliation suggestion with empty matches
        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "reconciliation",
            "payload_json": json.dumps({"matches": [], "unmatched_debit": [], "unmatched_credit": []}),
            "confidence": 0.0,
            "risk_score": 0.0,
            "requires_human": True,
            "agent_name": "opos_agent",
            "request_id": "test-apply",
        })
        case.action_apply_reconciliation()
        apply_logs = case.audit_log_ids.filtered(lambda rec: rec.action == "reconciliation_applied")
        self.assertEqual(len(apply_logs), 1)
