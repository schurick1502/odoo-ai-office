import base64
import csv
import io
import json

from odoo import models, fields


class AuditLogExport(models.TransientModel):
    _name = "account.ai.audit_log.export"
    _description = "Export AI Audit Logs"

    date_from = fields.Date(
        string="Date From",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string="Date To",
        required=True,
        default=fields.Date.today,
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

    def action_export(self):
        """Generate export file and return download action."""
        self.ensure_one()
        logs = self.env["account.ai.audit_log"].search([
            ("create_date", ">=", self.date_from),
            ("create_date", "<=", self.date_to),
        ], order="create_date asc")

        if self.export_format == "csv":
            content, filename = self._export_csv(logs)
        else:
            content, filename = self._export_json(logs)

        self.file_data = base64.b64encode(content.encode("utf-8"))
        self.file_name = filename

        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=%s&id=%d&field=file_data&filename_field=file_name&download=true"
            % (self._name, self.id),
            "target": "self",
        }

    def _log_to_dict(self, log):
        """Convert a single audit log record to a dictionary."""
        return {
            "date": str(log.create_date),
            "case_ref": log.case_id.name or "",
            "actor_type": log.actor_type or "",
            "actor": log.actor or "",
            "action": log.action or "",
            "before_json": log.before_json or "",
            "after_json": log.after_json or "",
        }

    def _export_csv(self, logs):
        """Export logs as CSV string."""
        output = io.StringIO()
        fieldnames = ["date", "case_ref", "actor_type", "actor", "action", "before_json", "after_json"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for log in logs:
            writer.writerow(self._log_to_dict(log))
        date_suffix = "%s_%s" % (self.date_from, self.date_to)
        return output.getvalue(), "audit_logs_%s.csv" % date_suffix

    def _export_json(self, logs):
        """Export logs as JSON string."""
        data = [self._log_to_dict(log) for log in logs]
        date_suffix = "%s_%s" % (self.date_from, self.date_to)
        return json.dumps(data, indent=2, ensure_ascii=False), "audit_logs_%s.json" % date_suffix
