import json

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestACL(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_group = cls.env.ref("account_ai_office.ai_office_user")
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")

        # Create a regular user (ai_office_user only, no approver)
        cls.regular_user = cls.env["res.users"].create({
            "name": "AI Office Test User",
            "login": "ai_office_test_user",
            "groups_id": [
                (6, 0, [
                    cls.user_group.id,
                    cls.env.ref("base.group_user").id,
                ]),
            ],
        })

        # Create an approver user
        cls.approver_user = cls.env["res.users"].create({
            "name": "AI Office Test Approver",
            "login": "ai_office_test_approver",
            "groups_id": [
                (6, 0, [
                    cls.approver_group.id,
                    cls.env.ref("base.group_user").id,
                ]),
            ],
        })

    def _create_case(self, user=None):
        env = self.env
        if user:
            env = self.env(user=user)
        return env["account.ai.case"].create({
            "name": "TEST-ACL-001",
            "partner_id": self.env.ref("base.res_partner_1").id,
            "period": "2024-01",
        })

    def _add_valid_suggestion(self, case):
        """Add a GoBD-compliant accounting_entry suggestion to the case."""
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
            "agent_name": "kontierung_agent",
            "request_id": "test-acl",
        })

    def test_user_cannot_approve(self):
        """Test that a user without approver group cannot approve a case."""
        # Create and propose as admin
        case = self._create_case()
        self._add_valid_suggestion(case)
        case.action_propose()
        self.assertEqual(case.state, "proposed")

        # Try to approve as regular user (fails on permission check before GoBD)
        case_as_user = case.with_user(self.regular_user)
        with self.assertRaises(UserError):
            case_as_user.action_approve()

    def test_user_cannot_post(self):
        """Test that a user without approver group cannot post a case."""
        # Create, propose, and approve as admin (who has approver rights)
        self.env.user.groups_id = [(4, self.approver_group.id)]
        case = self._create_case()
        self._add_valid_suggestion(case)
        case.action_propose()
        case.action_approve()
        self.assertEqual(case.state, "approved")

        # Try to post as regular user
        case_as_user = case.with_user(self.regular_user)
        with self.assertRaises(UserError):
            case_as_user.action_post()

    def test_approver_can_approve(self):
        """Test that a user with approver group can approve a case."""
        case = self._create_case()
        self._add_valid_suggestion(case)
        case.action_propose()
        self.assertEqual(case.state, "proposed")

        # Approve as approver user
        case_as_approver = case.with_user(self.approver_user)
        case_as_approver.action_approve()
        self.assertEqual(case.state, "approved")

    def test_approver_can_post(self):
        """Test that a user with approver group can post a case."""
        self.env.user.groups_id = [(4, self.approver_group.id)]
        case = self._create_case()
        self._add_valid_suggestion(case)
        case.action_propose()
        case.action_approve()
        self.assertEqual(case.state, "approved")

        # Post as approver user
        case_as_approver = case.with_user(self.approver_user)
        case_as_approver.action_post()
        self.assertEqual(case.state, "posted")

    def test_audit_log_immutable(self):
        """Test that non-superuser cannot delete audit logs."""
        self.env.user.groups_id = [(4, self.approver_group.id)]
        case = self._create_case()
        case.action_propose()
        log = case.audit_log_ids[0]

        # Regular user should not be able to delete
        log_as_user = log.with_user(self.regular_user)
        with self.assertRaises(UserError):
            log_as_user.unlink()
