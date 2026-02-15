import json

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestGoBDValidation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")
        cls.env.user.groups_id = [(4, cls.approver_group.id)]

    def _create_case_with_valid_suggestion(self, **overrides):
        """Create a case in 'proposed' state with a valid accounting_entry suggestion."""
        case = self.env["account.ai.case"].create({
            "name": "GOBD-001",
            "partner_id": self.env.ref("base.res_partner_1").id,
            "period": "2024-01",
        })
        suggestion_vals = {
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
            "agent_name": "kontierung_agent",
            "request_id": "test-gobd",
        }
        suggestion_vals.update(overrides)
        self.env["account.ai.suggestion"].create(suggestion_vals)
        case.state = "proposed"
        return case

    def test_approve_passes_with_valid_suggestion(self):
        """Approval succeeds when all GoBD checks pass."""
        case = self._create_case_with_valid_suggestion()
        case.action_approve()
        self.assertEqual(case.state, "approved")

    def test_approve_fails_without_suggestion(self):
        """Approval fails when no accounting_entry suggestion exists."""
        case = self.env["account.ai.case"].create({
            "name": "GOBD-NOSUG",
            "period": "2024-01",
        })
        case.state = "proposed"
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("No accounting entry suggestion", str(ctx.exception))

    def test_approve_fails_unbalanced(self):
        """Approval fails when debits != credits."""
        case = self._create_case_with_valid_suggestion(
            payload_json=json.dumps({
                "lines": [
                    {"account": "6300", "debit": 100.0, "credit": 0.0, "description": "Aufwand"},
                    {"account": "1600", "debit": 0.0, "credit": 50.0, "description": "Verbindlichkeiten"},
                ],
            })
        )
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("not balanced", str(ctx.exception))

    def test_approve_fails_missing_account(self):
        """Approval fails when a line is missing its account code."""
        case = self._create_case_with_valid_suggestion(
            payload_json=json.dumps({
                "lines": [
                    {"account": "", "debit": 100.0, "credit": 0.0, "description": "Aufwand"},
                    {"account": "1600", "debit": 0.0, "credit": 100.0, "description": "Verb."},
                ],
            })
        )
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("missing account", str(ctx.exception))

    def test_approve_fails_zero_amounts(self):
        """Approval fails when a line has zero debit and zero credit."""
        case = self._create_case_with_valid_suggestion(
            payload_json=json.dumps({
                "lines": [
                    {"account": "6300", "debit": 0.0, "credit": 0.0, "description": "Bad"},
                    {"account": "1600", "debit": 0.0, "credit": 0.0, "description": "Bad"},
                ],
            })
        )
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("debit or credit must be > 0", str(ctx.exception))

    def test_approve_fails_missing_description(self):
        """Approval fails when a line is missing its description (GoBD Buchungstext)."""
        case = self._create_case_with_valid_suggestion(
            payload_json=json.dumps({
                "lines": [
                    {"account": "6300", "debit": 119.0, "credit": 0.0, "description": ""},
                    {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "Verb."},
                ],
            })
        )
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("missing description", str(ctx.exception))

    def test_approve_fails_no_partner_for_verbindlichkeiten(self):
        """Approval fails when partner_id is missing for Verbindlichkeiten booking."""
        case = self.env["account.ai.case"].create({
            "name": "GOBD-NOPARTNER",
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
            "request_id": "test-nopartner",
        })
        case.state = "proposed"
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("Partner is required", str(ctx.exception))

    def test_approve_fails_low_confidence(self):
        """Approval fails when confidence is below policy threshold."""
        case = self._create_case_with_valid_suggestion(confidence=0.5)
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("Confidence", str(ctx.exception))
        self.assertIn("below", str(ctx.exception))

    def test_approve_fails_high_risk(self):
        """Approval fails when risk score exceeds policy maximum."""
        case = self._create_case_with_valid_suggestion(risk_score=0.8)
        with self.assertRaises(UserError) as ctx:
            case.action_approve()
        self.assertIn("Risk score", str(ctx.exception))
        self.assertIn("exceeds", str(ctx.exception))

    def test_approve_passes_with_good_thresholds(self):
        """Approval passes when confidence and risk are within policy limits."""
        case = self._create_case_with_valid_suggestion(
            confidence=0.85,
            risk_score=0.2,
        )
        case.action_approve()
        self.assertEqual(case.state, "approved")
