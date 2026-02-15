import base64
import json

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestTaxReport(TransactionCase):

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
                "name": "Purchase Journal (Tax Test)",
                "type": "purchase",
                "code": "TTPJ",
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

        cls.tax_account_19 = cls.env["account.account"].search([
            ("code", "=", "1576"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.tax_account_19:
            cls.tax_account_19 = cls.env["account.account"].create({
                "code": "1576",
                "name": "Abziehbare Vorsteuer 19%",
                "company_id": cls.env.company.id,
                "account_type": "asset_current",
            })

        cls.tax_account_7 = cls.env["account.account"].search([
            ("code", "=", "1571"),
            ("company_id", "=", cls.env.company.id),
        ], limit=1)
        if not cls.tax_account_7:
            cls.tax_account_7 = cls.env["account.account"].create({
                "code": "1571",
                "name": "Abziehbare Vorsteuer 7%",
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

    def _create_posted_case(self, name, period, net=100.0, tax_rate=0.19,
                            tax_account="1576"):
        """Create a posted case with configurable amounts and tax rate."""
        tax_amount = round(net * tax_rate, 2)
        gross = round(net + tax_amount, 2)
        case = self.env["account.ai.case"].create({
            "name": name,
            "partner_id": self.partner.id,
            "period": period,
        })
        self.env["account.ai.suggestion"].create({
            "case_id": case.id,
            "suggestion_type": "accounting_entry",
            "payload_json": json.dumps({
                "tax_rate": tax_rate,
                "lines": [
                    {"account": "6300", "debit": net, "credit": 0.0, "description": "Aufwand"},
                    {"account": tax_account, "debit": tax_amount, "credit": 0.0, "description": "Vorsteuer"},
                    {"account": "1600", "debit": 0.0, "credit": gross, "description": "Verbindlichkeiten"},
                ],
            }),
            "confidence": 0.9,
            "risk_score": 0.1,
            "requires_human": True,
            "agent_name": "test",
            "request_id": "tax-test",
        })
        case.action_propose()
        case.action_approve()
        case.action_post()
        return case

    def test_ustva_aggregates_19_percent(self):
        """UStVA correctly aggregates 19% net revenue and input VAT."""
        self._create_posted_case("TAX-19", "2024-07", net=100.0, tax_rate=0.19)
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-07",
            "report_type": "ustva",
        })
        data = wizard._generate_ustva_data()
        self.assertEqual(data["kz81"], 100.0)
        self.assertEqual(data["kz66"], 19.0)

    def test_ustva_aggregates_7_percent(self):
        """UStVA correctly aggregates 7% net revenue and input VAT."""
        self._create_posted_case("TAX-7", "2024-08", net=200.0, tax_rate=0.07,
                                 tax_account="1571")
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-08",
            "report_type": "ustva",
        })
        data = wizard._generate_ustva_data()
        self.assertEqual(data["kz86"], 200.0)
        self.assertEqual(data["kz61"], 14.0)

    def test_ustva_mixed_rates(self):
        """UStVA aggregates multiple cases with different tax rates."""
        self._create_posted_case("TAX-MIX1", "2024-09", net=100.0, tax_rate=0.19)
        self._create_posted_case("TAX-MIX2", "2024-09", net=200.0, tax_rate=0.07,
                                 tax_account="1571")
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-09",
            "report_type": "ustva",
        })
        data = wizard._generate_ustva_data()
        self.assertEqual(data["kz81"], 100.0)
        self.assertEqual(data["kz86"], 200.0)
        self.assertEqual(data["kz66"], 19.0)
        self.assertEqual(data["kz61"], 14.0)

    def test_ustva_vorauszahlung_calculation(self):
        """KZ 83 (Vorauszahlung) = (KZ81_tax + KZ86_tax) - (KZ66 + KZ61)."""
        self._create_posted_case("TAX-VP", "2024-10", net=100.0, tax_rate=0.19)
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-10",
            "report_type": "ustva",
        })
        data = wizard._generate_ustva_data()
        # KZ81_tax = 100 * 0.19 = 19, KZ66 = 19 → KZ83 = 19 - 19 = 0
        self.assertEqual(data["kz83"], 0.0)

    def test_ustva_empty_period_raises(self):
        """UStVA raises UserError for period with no cases."""
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2099-01",
            "report_type": "ustva",
        })
        with self.assertRaises(UserError):
            wizard._generate_ustva_data()

    def test_ustva_csv_format(self):
        """UStVA CSV export contains Kennziffern with semicolons."""
        self._create_posted_case("TAX-CSV", "2024-11", net=100.0, tax_rate=0.19)
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-11",
            "report_type": "ustva",
            "export_format": "csv",
        })
        wizard.action_generate()
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        self.assertIn("81;", content)
        self.assertIn("Vorauszahlung", content)
        self.assertIn(";", content)

    def test_ustva_json_format(self):
        """UStVA JSON export contains all Kennziffern."""
        self._create_posted_case("TAX-JSON", "2024-12", net=100.0, tax_rate=0.19)
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-12",
            "report_type": "ustva",
            "export_format": "json",
        })
        wizard.action_generate()
        content = base64.b64decode(wizard.file_data).decode("utf-8")
        data = json.loads(content)
        self.assertIn("kz81", data)
        self.assertIn("kz83", data)
        self.assertEqual(data["kz81"], 100.0)

    def test_zm_empty_placeholder(self):
        """ZM report raises UserError (not yet implemented)."""
        wizard = self.env["account.ai.tax.report"].create({
            "period": "2024-01",
            "report_type": "zm",
        })
        with self.assertRaises(UserError):
            wizard.action_generate()
