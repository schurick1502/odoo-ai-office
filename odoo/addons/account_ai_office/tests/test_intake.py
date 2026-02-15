import base64

from odoo.tests.common import TransactionCase


class TestEmailIntake(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_group = cls.env.ref("account_ai_office.ai_office_user")
        cls.env.user.groups_id = [(4, cls.user_group.id)]

    def _create_case(self, **kwargs):
        vals = {"name": "INTAKE-TEST"}
        vals.update(kwargs)
        return self.env["account.ai.case"].create(vals)

    # ── message_new ─────────────────────────────────────────────────

    def test_message_new_creates_case(self):
        """message_new creates a case in 'new' state."""
        msg = {
            "email_from": "supplier@example.com",
            "subject": "Invoice 2024-01",
            "body": "Please find attached.",
        }
        case = self.env["account.ai.case"].message_new(msg)
        self.assertTrue(case.exists())
        self.assertEqual(case.state, "new")

    def test_message_new_matches_existing_partner(self):
        """message_new finds existing partner by email."""
        partner = self.env["res.partner"].create({
            "name": "Existing Supplier",
            "email": "existing@example.com",
        })
        msg = {"email_from": "existing@example.com", "subject": "Test"}
        case = self.env["account.ai.case"].message_new(msg)
        self.assertEqual(case.partner_id, partner)

    def test_message_new_creates_partner_if_not_found(self):
        """message_new creates a new partner when no match found."""
        msg = {"email_from": "brand-new@example.com", "subject": "Test"}
        case = self.env["account.ai.case"].message_new(msg)
        self.assertTrue(case.partner_id.exists())
        self.assertEqual(case.partner_id.email, "brand-new@example.com")
        self.assertEqual(case.partner_id.supplier_rank, 1)

    def test_message_new_audit_log(self):
        """message_new writes an audit log entry with actor_type='agent'."""
        msg = {"email_from": "audit@example.com", "subject": "Test"}
        case = self.env["account.ai.case"].message_new(msg)
        intake_logs = case.audit_log_ids.filtered(
            lambda rec: rec.action == "email_intake"
        )
        self.assertEqual(len(intake_logs), 1)
        self.assertEqual(intake_logs[0].actor_type, "agent")
        self.assertEqual(intake_logs[0].actor, "mail_intake")

    def test_message_new_case_insensitive_email(self):
        """Partner matching is case-insensitive."""
        partner = self.env["res.partner"].create({
            "name": "Case Test",
            "email": "Test@Example.COM",
        })
        msg = {"email_from": "test@example.com", "subject": "Test"}
        case = self.env["account.ai.case"].message_new(msg)
        self.assertEqual(case.partner_id, partner)

    # ── _get_or_create_partner ──────────────────────────────────────

    def test_get_or_create_partner_empty_email(self):
        """_get_or_create_partner returns empty recordset for falsy email."""
        case = self._create_case()
        result = case._get_or_create_partner("")
        self.assertFalse(result.exists())

    def test_get_or_create_partner_uses_display_name(self):
        """_get_or_create_partner uses provided name for new partner."""
        case = self._create_case()
        partner = case._get_or_create_partner("new@test.com", name="Acme GmbH")
        self.assertEqual(partner.name, "Acme GmbH")
        self.assertEqual(partner.email, "new@test.com")

    # ── _filter_attachments ─────────────────────────────────────────

    def test_filter_attachments_accepts_pdf(self):
        """_filter_attachments accepts PDF files."""
        case = self._create_case()
        pdf = self.env["ir.attachment"].create({
            "name": "invoice.pdf",
            "mimetype": "application/pdf",
            "datas": base64.b64encode(b"fake pdf"),
        })
        filtered = case._filter_attachments(pdf)
        self.assertIn(pdf, filtered)

    def test_filter_attachments_rejects_exe(self):
        """_filter_attachments rejects executable files."""
        case = self._create_case()
        exe = self.env["ir.attachment"].create({
            "name": "malware.exe",
            "mimetype": "application/x-msdownload",
            "datas": base64.b64encode(b"fake exe"),
        })
        filtered = case._filter_attachments(exe)
        self.assertNotIn(exe, filtered)

    def test_allowed_mimetypes_comprehensive(self):
        """Verify all expected MIME types are in the allowed set."""
        from odoo.addons.account_ai_office.models.ai_case import AiCase
        expected = {
            "application/pdf", "application/xml", "text/xml",
            "image/png", "image/jpeg", "image/tiff", "image/bmp",
        }
        self.assertEqual(AiCase.ALLOWED_ATTACHMENT_MIMETYPES, expected)
