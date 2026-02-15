from odoo import models, fields, _
from odoo.exceptions import UserError


class AiAuditLog(models.Model):
    _name = "account.ai.audit_log"
    _description = "AI Office Audit Log"
    _order = "create_date desc"

    case_id = fields.Many2one(
        "account.ai.case",
        string="Case",
        required=True,
        ondelete="cascade",
    )
    actor_type = fields.Selection(
        [
            ("user", "User"),
            ("agent", "Agent"),
        ],
        string="Actor Type",
        required=True,
    )
    actor = fields.Char(
        string="Actor",
        required=True,
        help="User name or agent identifier.",
    )
    action = fields.Char(
        string="Action",
        required=True,
    )
    before_json = fields.Text(
        string="Before (JSON)",
    )
    after_json = fields.Text(
        string="After (JSON)",
    )
    source_refs = fields.Text(
        string="Source References",
    )
    request_id = fields.Char(
        string="Request ID",
    )
    company_id = fields.Many2one(
        related="case_id.company_id",
        string="Company",
        store=True,
    )

    def unlink(self):
        """Prevent deletion of audit logs except by superuser."""
        if not self.env.is_superuser():
            raise UserError(_("Audit logs cannot be deleted. They are immutable for compliance reasons."))
        return super().unlink()
