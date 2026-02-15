from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestStateMachine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")
        # Ensure the test user has approver rights for valid transition tests
        cls.env.user.groups_id = [(4, cls.approver_group.id)]

    def _create_case(self, **kwargs):
        vals = {
            "name": "TEST-001",
            "partner_id": self.env.ref("base.res_partner_1").id,
            "period": "2024-01",
        }
        vals.update(kwargs)
        return self.env["account.ai.case"].create(vals)

    def test_create_case(self):
        """Test that a newly created case has state 'new'."""
        case = self._create_case()
        self.assertEqual(case.state, "new")

    def test_valid_transitions(self):
        """Test the full happy path: new -> proposed -> approved -> posted -> exported."""
        case = self._create_case()
        self.assertEqual(case.state, "new")

        case.action_propose()
        self.assertEqual(case.state, "proposed")

        case.action_approve()
        self.assertEqual(case.state, "approved")

        case.action_post()
        self.assertEqual(case.state, "posted")

        case.action_export()
        self.assertEqual(case.state, "exported")

    def test_invalid_approve_from_new(self):
        """Test that approving directly from 'new' raises an error."""
        case = self._create_case()
        self.assertEqual(case.state, "new")
        with self.assertRaises(UserError):
            case.action_approve()

    def test_needs_attention(self):
        """Test that needs_attention can be set from any state."""
        case = self._create_case()
        self.assertEqual(case.state, "new")

        case.action_needs_attention()
        self.assertEqual(case.state, "needs_attention")

        # Reset and try from proposed
        case.action_reset_to_new()
        self.assertEqual(case.state, "new")

        case.action_propose()
        case.action_needs_attention()
        self.assertEqual(case.state, "needs_attention")

    def test_audit_log_created(self):
        """Test that an audit log entry is created after action_propose."""
        case = self._create_case()
        self.assertEqual(len(case.audit_log_ids), 0)

        case.action_propose()
        self.assertEqual(len(case.audit_log_ids), 1)

        log = case.audit_log_ids[0]
        self.assertEqual(log.action, "propose")
        self.assertEqual(log.actor_type, "user")
        self.assertEqual(log.actor, self.env.user.name)

    def test_reset_only_from_needs_attention_or_failed(self):
        """Test that reset_to_new only works from needs_attention or failed."""
        case = self._create_case()
        case.action_propose()
        with self.assertRaises(UserError):
            case.action_reset_to_new()

    def test_export_only_from_posted(self):
        """Test that export only works from posted state."""
        case = self._create_case()
        with self.assertRaises(UserError):
            case.action_export()

    def test_suggestion_count(self):
        """Test that suggestion_count is computed correctly."""
        case = self._create_case()
        self.assertEqual(case.suggestion_count, 0)

        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "classification",
            "confidence": 0.95,
        })
        case.invalidate_recordset()
        self.assertEqual(case.suggestion_count, 1)
