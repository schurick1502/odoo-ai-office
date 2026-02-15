import base64
import json

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestExportIntegration(TransactionCase):
    """End-to-end export integration tests covering the full case→export flow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver_group = cls.env.ref("account_ai_office.ai_office_approver")
        cls.env.user.groups_id = [(4, cls.approver_group.id)]

        cls.journal = cls.env["account.journal"].search([
            ("type", "=", "purchase"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.journal:
            cls.journal = cls.env["account.journal"].create({
                "name": "Purchase Journal (E2E Export)",
                "type": "purchase",
                "code": "TEPJ",
                "company_id": cls.env.company.id,
            })

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

    def _create_posted_case(self, name, period="2024-01", tax_rate=0.19,
                            invoice_date=None, invoice_number=None):
        """Create a fully posted case with optional enrichment."""
        case = self.env["account.ai.case"].create({
            "name": name,
            "partner_id": self.partner.id,
            "period": period,
        })
        payload = {
            "tax_rate": tax_rate,
            "lines": [
                {"account": "6300", "debit": 100.0, "credit": 0.0, "description": "Aufwand"},
                {"account": "1576", "debit": 19.0, "credit": 0.0, "description": "Vorsteuer 19%"},
                {"account": "1600", "debit": 0.0, "credit": 119.0, "description": "Verbindlichkeiten"},
            ],
        }
        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "accounting_entry",
            "payload_json": json.dumps(payload),
            "confidence": 0.9,
            "risk_score": 0.1,
            "requires_human": True,
            "agent_name": "test",
            "request_id": "e2e-export",
        })
        if invoice_date:
            self.env["account.ai.suggestion"].create({
                "case_id": case.id,
                "suggestion_type": "enrichment",
                "payload_json": json.dumps({"field": "invoice_date", "value": invoice_date}),
                "confidence": 0.9,
                "risk_score": 0.0,
                "requires_human": True,
                "agent_name": "enrichment_agent",
                "request_id": "e2e-export",
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
                "request_id": "e2e-export",
            })
        case.action_propose()
        case.action_approve()
        case.action_post()
        return case

    def test_full_flow_case_to_datev(self):
        """Full flow: new → proposed → approved → posted → exported with DATEV file."""
        case = self._create_posted_case("E2E-FULL", invoice_date="2024-01-15",
                                        invoice_number="RE-2024-001")
        self.assertEqual(case.state, "posted")
        self.assertTrue(case.move_id)

        case.action_export()
        self.assertEqual(case.state, "exported")
        self.assertTrue(case.datev_file_id)

        content = base64.b64decode(case.datev_file_id.datas).decode("utf-8")
        self.assertIn("119,00", content)
        self.assertIn("6300", content)
        self.assertIn("RE-2024-001", content)
        self.assertIn("1501", content)  # Date 2024-01-15 → DDMM = 1501

    def test_export_reexport_blocked(self):
        """Already exported case cannot be exported again."""
        case = self._create_posted_case("E2E-REEXP")
        case.action_export()
        self.assertEqual(case.state, "exported")
        with self.assertRaises(UserError):
            case.action_export()

    def test_batch_wizard_exports_multiple(self):
        """Batch wizard exports multiple cases and transitions them to exported."""
        c1 = self._create_posted_case("E2E-B1", period="2024-02")
        c2 = self._create_posted_case("E2E-B2", period="2024-02")
        c3 = self._create_posted_case("E2E-B3", period="2024-02")

        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-02",
            "period_to": "2024-02",
            "export_format": "datev",
        })
        wizard.action_export()

        for case in (c1, c2, c3):
            case.invalidate_recordset()
            self.assertEqual(case.state, "exported")

    def test_batch_datev_csv_has_all_rows(self):
        """Batch DATEV CSV has header + one data row per case."""
        self._create_posted_case("E2E-R1", period="2024-03")
        self._create_posted_case("E2E-R2", period="2024-03")

        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-03",
            "period_to": "2024-03",
            "export_format": "datev",
        })
        wizard.action_export()
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        lines = [l for l in content.split("\r\n") if l.strip()]
        # Header + 2 data rows
        self.assertEqual(len(lines), 3)

    def test_batch_wizard_period_range(self):
        """Batch wizard finds cases across multiple periods."""
        self._create_posted_case("E2E-PR1", period="2024-04")
        self._create_posted_case("E2E-PR2", period="2024-05")
        self._create_posted_case("E2E-PR3", period="2024-09")  # Outside range

        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-04",
            "period_to": "2024-06",
            "export_format": "datev",
        })
        wizard.action_export()
        self.assertEqual(wizard.case_count, 2)

    def test_batch_include_exported(self):
        """Batch wizard with include_exported=True includes already exported cases."""
        case = self._create_posted_case("E2E-IE", period="2024-07")
        case.action_export()

        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-07",
            "period_to": "2024-07",
            "include_exported": True,
        })
        cases = wizard._find_cases()
        self.assertIn(case, cases)

    def test_ustva_from_posted_cases(self):
        """UStVA wizard generates correct Kennziffern from posted cases."""
        self._create_posted_case("E2E-TAX", period="2024-08", tax_rate=0.19)
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-08",
            "report_type": "ustva",
            "export_format": "json",
        })
        wizard.action_generate()
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        data = json.loads(content)
        self.assertEqual(data["kz81"], 100.0)
        self.assertEqual(data["kz66"], 19.0)

    def test_export_audit_trail_complete(self):
        """Exported case has complete audit trail from propose through export."""
        case = self._create_posted_case("E2E-AUDIT")
        case.action_export()

        actions = case.audit_log_ids.mapped("action")
        self.assertIn("propose", actions)
        self.assertIn("approve", actions)
        self.assertIn("post", actions)
        self.assertIn("export", actions)

        export_log = case.audit_log_ids.filtered(lambda rec: rec.action == "export")
        after = json.loads(export_log.after_json)
        self.assertIn("datev_file_id", after)
        self.assertIn("datev_filename", after)
