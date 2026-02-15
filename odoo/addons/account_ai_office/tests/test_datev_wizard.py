import base64
import json

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestDatevWizard(TransactionCase):

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
                "name": "Purchase Journal (Wizard Test)",
                "type": "purchase",
                "code": "TWPJ",
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

    def _create_posted_case(self, name="WIZ-001", period="2024-01"):
        """Create a posted case with a valid move."""
        case = self.env["account.ai.case"].create({
            "name": name,
            "partner_id": self.partner.id,
            "period": period,
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
            "request_id": "wizard-test",
        })
        case.action_propose()
        case.action_approve()
        case.action_post()
        return case

    def test_find_cases_by_period(self):
        """_find_cases returns posted cases matching the period range."""
        case1 = self._create_posted_case(name="WIZ-P1", period="2024-01")
        case2 = self._create_posted_case(name="WIZ-P2", period="2024-02")
        self._create_posted_case(name="WIZ-P3", period="2024-06")  # Outside range

        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-01",
            "period_to": "2024-03",
        })
        cases = wizard._find_cases()
        case_names = cases.mapped("name")
        self.assertIn("WIZ-P1", case_names)
        self.assertIn("WIZ-P2", case_names)
        self.assertNotIn("WIZ-P3", case_names)

    def test_export_datev_creates_file(self):
        """action_export generates a DATEV file with binary data."""
        self._create_posted_case(name="WIZ-EXP", period="2024-01")
        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-01",
            "period_to": "2024-01",
            "export_format": "datev",
        })
        wizard.action_export()
        self.assertTrue(wizard.file_data)
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        self.assertIn("119,00", content)

    def test_export_transitions_posted_to_exported(self):
        """action_export transitions posted cases to exported."""
        case = self._create_posted_case(name="WIZ-TRANS", period="2024-03")
        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-03",
            "period_to": "2024-03",
            "export_format": "datev",
        })
        wizard.action_export()
        case.invalidate_recordset()
        self.assertEqual(case.state, "exported")

    def test_export_no_cases_raises(self):
        """action_export raises UserError when no cases match."""
        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2099-01",
            "period_to": "2099-12",
        })
        with self.assertRaises(UserError):
            wizard.action_export()

    def test_include_exported_flag(self):
        """include_exported=True includes already exported cases."""
        case = self._create_posted_case(name="WIZ-INCL", period="2024-04")
        case.action_export()  # Now state=exported
        self.assertEqual(case.state, "exported")

        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-04",
            "period_to": "2024-04",
            "include_exported": False,
        })
        cases = wizard._find_cases()
        self.assertNotIn(case, cases)

        wizard.include_exported = True
        cases = wizard._find_cases()
        self.assertIn(case, cases)

    def test_standard_csv_export(self):
        """Standard CSV export generates summary with case details."""
        self._create_posted_case(name="WIZ-STD", period="2024-05")
        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-05",
            "period_to": "2024-05",
            "export_format": "csv",
        })
        wizard.action_export()
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        self.assertIn("WIZ-STD", content)
        self.assertIn("case_ref", content)

    def test_preview_counts_cases(self):
        """action_preview sets case_count without generating a file."""
        self._create_posted_case(name="WIZ-PRE1", period="2024-06")
        self._create_posted_case(name="WIZ-PRE2", period="2024-06")
        wizard = self.env["account.ai.datev.export"].create({
            "period_from": "2024-06",
            "period_to": "2024-06",
        })
        wizard.action_preview()
        self.assertEqual(wizard.case_count, 2)
        self.assertFalse(wizard.file_data)
