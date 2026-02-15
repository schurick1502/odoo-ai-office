import base64
import csv
import io
import json

from odoo import api, models, fields, _
from odoo.exceptions import UserError


class TaxReport(models.TransientModel):
    _name = "account.ai.tax.report"
    _description = "Tax Report (UStVA/ZM)"

    period = fields.Char(
        string="Period",
        required=True,
        default=lambda self: self._default_period(),
    )
    report_type = fields.Selection(
        [
            ("ustva", "UStVA (Umsatzsteuervoranmeldung)"),
            ("zm", "ZM (Zusammenfassende Meldung)"),
        ],
        string="Report Type",
        required=True,
        default="ustva",
    )
    export_format = fields.Selection(
        [
            ("csv", "CSV"),
            ("json", "JSON"),
        ],
        string="Format",
        required=True,
        default="csv",
    )
    file_data = fields.Binary(
        string="File",
        readonly=True,
    )
    file_name = fields.Char(
        string="Filename",
        readonly=True,
    )

    @api.model
    def _default_period(self):
        """Default to previous month."""
        today = fields.Date.today()
        if today.month == 1:
            return "%d-12" % (today.year - 1)
        return "%d-%02d" % (today.year, today.month - 1)

    def _find_cases(self):
        """Find posted/exported cases for the period."""
        self.ensure_one()
        return self.env["account.ai.case"].search([
            ("period", "=", self.period),
            ("state", "in", ["posted", "exported"]),
            ("move_id", "!=", False),
        ])

    def _generate_ustva_data(self):
        """Aggregate tax data into UStVA Kennziffern.

        Returns a dict with keys: kz81, kz86, kz66, kz61, kz83 and their values.
        - KZ 81: Net revenue at 19%
        - KZ 86: Net revenue at 7%
        - KZ 66: Input VAT 19% (Vorsteuer)
        - KZ 61: Input VAT 7% (Vorsteuer)
        - KZ 83: VAT prepayment = (KZ81_tax + KZ86_tax) - (KZ66 + KZ61)
        """
        self.ensure_one()
        cases = self._find_cases()
        if not cases:
            raise UserError(
                _("No posted/exported cases found for period %s.") % self.period
            )

        kz81_net = 0.0  # Net 19%
        kz86_net = 0.0  # Net 7%
        kz66 = 0.0      # Vorsteuer 19%
        kz61 = 0.0      # Vorsteuer 7%

        for case in cases:
            suggestion = case.suggestion_ids.filtered(
                lambda s: s.suggestion_type == "accounting_entry"
            )[:1]
            if not suggestion:
                continue
            try:
                payload = json.loads(suggestion.payload_json or "{}")
            except (json.JSONDecodeError, TypeError):
                continue

            tax_rate = payload.get("tax_rate")
            lines = payload.get("lines", [])

            # Calculate net amounts (expense lines) and tax amounts
            net_amount = 0.0
            tax_amount = 0.0
            for line in lines:
                account = line.get("account", "")
                debit = line.get("debit", 0.0)
                credit = line.get("credit", 0.0)
                amount = debit or credit
                if account in self.env["account.ai.case"].DATEV_TAX_ACCOUNTS:
                    tax_amount += amount
                elif account not in self.env["account.ai.case"].DATEV_CONTRA_ACCOUNTS:
                    net_amount += amount

            # Determine rate from payload or tax account
            if tax_rate is None:
                for line in lines:
                    account = line.get("account", "")
                    if account in self.env["account.ai.case"].DATEV_TAX_ACCOUNTS:
                        tax_rate = self.env["account.ai.case"].DATEV_TAX_ACCOUNTS[account]
                        break

            if tax_rate == 0.19:
                kz81_net += net_amount
                kz66 += tax_amount
            elif tax_rate == 0.07:
                kz86_net += net_amount
                kz61 += tax_amount

        # KZ 83: VAT prepayment
        kz81_tax = kz81_net * 0.19
        kz86_tax = kz86_net * 0.07
        kz83 = (kz81_tax + kz86_tax) - (kz66 + kz61)

        return {
            "period": self.period,
            "kz81": round(kz81_net, 2),
            "kz86": round(kz86_net, 2),
            "kz66": round(kz66, 2),
            "kz61": round(kz61, 2),
            "kz83": round(kz83, 2),
            "kz81_tax": round(kz81_tax, 2),
            "kz86_tax": round(kz86_tax, 2),
        }

    def _generate_zm_data(self):
        """Generate ZM data (placeholder for future implementation)."""
        return []

    def action_generate(self):
        """Generate the tax report and return download action."""
        self.ensure_one()

        if self.report_type == "ustva":
            data = self._generate_ustva_data()
            if self.export_format == "csv":
                content, filename = self._ustva_to_csv(data)
            else:
                content, filename = self._ustva_to_json(data)
        else:
            data = self._generate_zm_data()
            if not data:
                raise UserError(_("ZM report is not yet implemented."))
            content = json.dumps(data, indent=2)
            filename = "zm_%s.json" % self.period

        self.file_data = base64.b64encode(content.encode("utf-8"))
        self.file_name = filename

        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=%s&id=%d&field=file_data&filename_field=file_name&download=true"
            % (self._name, self.id),
            "target": "self",
        }

    def _ustva_to_csv(self, data):
        """Convert UStVA data dict to CSV."""
        output = io.StringIO()
        fieldnames = ["Kennziffer", "Bezeichnung", "Betrag"]
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        rows = [
            {"Kennziffer": "81", "Bezeichnung": "Steuerpflichtige Umsaetze 19%", "Betrag": "%.2f" % data["kz81"]},
            {"Kennziffer": "86", "Bezeichnung": "Steuerpflichtige Umsaetze 7%", "Betrag": "%.2f" % data["kz86"]},
            {"Kennziffer": "66", "Bezeichnung": "Vorsteuer 19%", "Betrag": "%.2f" % data["kz66"]},
            {"Kennziffer": "61", "Bezeichnung": "Vorsteuer 7%", "Betrag": "%.2f" % data["kz61"]},
            {"Kennziffer": "83", "Bezeichnung": "Vorauszahlung", "Betrag": "%.2f" % data["kz83"]},
        ]
        for row in rows:
            writer.writerow(row)
        return output.getvalue(), "ustva_%s.csv" % data["period"]

    def _ustva_to_json(self, data):
        """Convert UStVA data dict to JSON."""
        return json.dumps(data, indent=2, ensure_ascii=False), "ustva_%s.json" % data["period"]
