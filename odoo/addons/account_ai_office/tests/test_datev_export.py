import base64
import json

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestDatevExport(TransactionCase):

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
                "name": "Purchase Journal (DATEV Test)",
                "type": "purchase",
                "code": "TDPJ",
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

    def _create_posted_case(self, name="DATEV-001", period="2024-01",
                            invoice_date=None, invoice_number=None,
                            tax_rate=None):
        """Create a case through propose → approve → post with optional enrichment."""
        case = self.env["account.ai.case"].create({
            "name": name,
            "partner_id": self.partner.id,
            "period": period,
        })
        payload = {
            "lines": [
                {"account": "6300", "debit": 100.0, "credit": 0.0, "description": "Aufwand"},
                {"account": "1576", "debit": 19.0, "credit": 0.0, "description": "Vorsteuer 19%"},
                {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "Verbindlichkeiten"},
            ],
        }
        if tax_rate is not None:
            payload["tax_rate"] = tax_rate
        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "accounting_entry",
            "payload_json": json.dumps(payload),
            "confidence": 0.9,
            "risk_score": 0.1,
            "requires_human": True,
            "agent_name": "test",
            "request_id": "datev-test",
        })
        # Add enrichment suggestions if provided
        if invoice_date:
            self.env["account.ai.suggestion"].create({
                "case_id": case.id,
                "suggestion_type": "enrichment",
                "payload_json": json.dumps({"field": "invoice_date", "value": invoice_date}),
                "confidence": 0.9,
                "risk_score": 0.0,
                "requires_human": True,
                "agent_name": "enrichment_agent",
                "request_id": "datev-test",
            })
        if invoice_number:
            self.env["account.ai.suggestion"].create({
                "case_id": case.id,
                "suggestion_type": "enrichment",
                "payload_json": json.dumps({"field": "invoice_number", "value": invoice_number}),
                "confidence": 0.9,
                "risk_score": 0.0,
                "requires_human": True,
                "agent_name": "enrichment_agent",
                "request_id": "datev-test",
            })
        case.action_propose()
        case.action_approve()
        case.action_post()
        return case

    # ── _format_datev_amount ──────────────────────────────────────

    def test_format_datev_amount(self):
        """_format_datev_amount converts floats to German decimal format."""
        AiCase = self.env["account.ai.case"]
        self.assertEqual(AiCase._format_datev_amount(119.0), "119,00")
        self.assertEqual(AiCase._format_datev_amount(-100), "100,00")
        self.assertEqual(AiCase._format_datev_amount(0.0), "0,00")
        self.assertEqual(AiCase._format_datev_amount(1234.56), "1234,56")

    # ── _get_datev_tax_key ────────────────────────────────────────

    def test_datev_tax_key_from_suggestion(self):
        """_get_datev_tax_key returns '9' when tax_rate=0.19 in suggestion payload."""
        case = self._create_posted_case(tax_rate=0.19)
        self.assertEqual(case._get_datev_tax_key(), "9")

    def test_datev_tax_key_fallback_from_account(self):
        """_get_datev_tax_key falls back to tax account detection (1576 → '9')."""
        case = self._create_posted_case()  # No tax_rate in payload
        self.assertEqual(case._get_datev_tax_key(), "9")

    # ── _generate_datev_lines ─────────────────────────────────────

    def test_generate_datev_lines_single_expense(self):
        """Single expense line produces one DATEV line with gross amount."""
        case = self._create_posted_case()
        lines = case._generate_datev_lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["Umsatz (Soll/Haben)"], "119,00")
        self.assertEqual(lines[0]["Konto"], "6300")
        self.assertEqual(lines[0]["Gegenkonto (ohne BU-Schluessel)"], "1600")
        self.assertEqual(lines[0]["BU-Schluessel"], "9")
        self.assertEqual(lines[0]["Soll/Haben-Kennzeichen"], "S")

    def test_generate_datev_lines_date_format(self):
        """Belegdatum is formatted as DDMM from enrichment invoice_date."""
        case = self._create_posted_case(invoice_date="2024-03-15")
        lines = case._generate_datev_lines()
        self.assertEqual(lines[0]["Belegdatum"], "1503")

    def test_generate_datev_lines_document_ref(self):
        """Belegfeld 1 uses enrichment invoice_number when available."""
        case = self._create_posted_case(invoice_number="RE-2024-001")
        lines = case._generate_datev_lines()
        self.assertEqual(lines[0]["Belegfeld 1"], "RE-2024-001")

    # ── _generate_datev_csv ───────────────────────────────────────

    def test_generate_datev_csv_has_header(self):
        """CSV output starts with DATEV header columns."""
        case = self._create_posted_case()
        csv_content = case._generate_datev_csv()
        first_line = csv_content.split("\r\n")[0]
        self.assertIn("Umsatz (Soll/Haben)", first_line)
        self.assertIn("BU-Schluessel", first_line)
        self.assertIn("Buchungstext", first_line)

    def test_generate_datev_csv_semicolon(self):
        """CSV uses semicolon delimiter and has 14 columns."""
        case = self._create_posted_case()
        csv_content = case._generate_datev_csv()
        data_line = csv_content.split("\r\n")[1]
        columns = data_line.split(";")
        self.assertEqual(len(columns), 14)

    # ── action_export ─────────────────────────────────────────────

    def test_action_export_creates_attachment(self):
        """action_export creates DATEV attachment and transitions to exported."""
        case = self._create_posted_case()
        case.action_export()
        self.assertEqual(case.state, "exported")
        self.assertTrue(case.datev_file_id)
        self.assertIn("DATEV", case.datev_file_id.name)

    def test_action_export_attachment_content(self):
        """DATEV attachment contains expected CSV data."""
        case = self._create_posted_case()
        case.action_export()
        content = base64.b64decode(case.datev_file_id.datas).decode("utf-8")
        self.assertIn("119,00", content)
        self.assertIn("6300", content)
        self.assertIn("1600", content)

    def test_action_export_requires_move_id(self):
        """action_export raises UserError if case has no move_id."""
        case = self.env["account.ai.case"].create({
            "name": "DATEV-NOMOVE",
            "partner_id": self.partner.id,
            "period": "2024-01",
        })
        case.state = "posted"
        with self.assertRaises(UserError):
            case.action_export()

    def test_action_export_audit_log(self):
        """action_export audit log contains datev_file_id."""
        case = self._create_posted_case()
        case.action_export()
        export_logs = case.audit_log_ids.filtered(lambda rec: rec.action == "export")
        self.assertEqual(len(export_logs), 1)
        after = json.loads(export_logs.after_json)
        self.assertIn("datev_file_id", after)
        self.assertEqual(after["datev_file_id"], case.datev_file_id.id)
