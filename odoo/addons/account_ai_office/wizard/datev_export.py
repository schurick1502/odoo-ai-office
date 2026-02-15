import base64
import csv
import io

from odoo import models, fields, _
from odoo.exceptions import UserError


class DatevExport(models.TransientModel):
    _name = "account.ai.datev.export"
    _description = "DATEV Batch Export"

    period_from = fields.Char(
        string="Period From",
        required=True,
        default=lambda self: fields.Date.today().strftime("%Y-%m"),
    )
    period_to = fields.Char(
        string="Period To",
        required=True,
        default=lambda self: fields.Date.today().strftime("%Y-%m"),
    )
    export_format = fields.Selection(
        [
            ("datev", "DATEV CSV"),
            ("csv", "Standard CSV"),
        ],
        string="Format",
        required=True,
        default="datev",
    )
    include_exported = fields.Boolean(
        string="Include Already Exported",
        default=False,
    )
    file_data = fields.Binary(
        string="File",
        readonly=True,
    )
    file_name = fields.Char(
        string="Filename",
        readonly=True,
    )
    case_count = fields.Integer(
        string="Cases Found",
        readonly=True,
    )

    def _find_cases(self):
        """Find cases matching the period range and state criteria."""
        self.ensure_one()
        states = ["posted"]
        if self.include_exported:
            states.append("exported")
        domain = [
            ("period", ">=", self.period_from),
            ("period", "<=", self.period_to),
            ("state", "in", states),
            ("move_id", "!=", False),
        ]
        return self.env["account.ai.case"].search(domain, order="period asc, name asc")

    def action_preview(self):
        """Count matching cases without exporting."""
        self.ensure_one()
        cases = self._find_cases()
        self.case_count = len(cases)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_export(self):
        """Generate export file, transition cases, and return download."""
        self.ensure_one()
        cases = self._find_cases()
        if not cases:
            raise UserError(_("No cases found for the selected period and criteria."))

        if self.export_format == "datev":
            content, filename = self._export_datev(cases)
        else:
            content, filename = self._export_standard_csv(cases)

        # Transition posted cases to exported
        for case in cases.filtered(lambda c: c.state == "posted"):
            case.action_export()

        self.file_data = base64.b64encode(content.encode("utf-8"))
        self.file_name = filename
        self.case_count = len(cases)

        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=%s&id=%d&field=file_data&filename_field=file_name&download=true"
            % (self._name, self.id),
            "target": "self",
        }

    def _export_datev(self, cases):
        """Generate DATEV CSV for multiple cases."""
        # Delegate to the case model's CSV generator
        csv_content = cases[0]._generate_datev_csv(cases)
        filename = "DATEV_export_%s_%s.csv" % (self.period_from, self.period_to)
        return csv_content, filename

    def _export_standard_csv(self, cases):
        """Generate a standard summary CSV for multiple cases."""
        output = io.StringIO()
        fieldnames = [
            "case_ref", "period", "partner", "invoice_date",
            "total_debit", "total_credit", "state",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            enrichment = case._get_enrichment_context()
            total_debit = sum(line.debit for line in case.move_id.line_ids) if case.move_id else 0.0
            total_credit = sum(line.credit for line in case.move_id.line_ids) if case.move_id else 0.0
            writer.writerow({
                "case_ref": case.name,
                "period": case.period or "",
                "partner": case.partner_id.name or "",
                "invoice_date": enrichment.get("invoice_date", ""),
                "total_debit": "%.2f" % total_debit,
                "total_credit": "%.2f" % total_credit,
                "state": case.state,
            })
        filename = "export_%s_%s.csv" % (self.period_from, self.period_to)
        return output.getvalue(), filename
