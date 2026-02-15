from odoo import models, fields


class AiPolicy(models.Model):
    _name = "account.ai.policy"
    _description = "AI Office Policy"
    _order = "name"

    name = fields.Char(
        string="Name",
        required=True,
    )
    scope = fields.Selection(
        [
            ("company", "Company"),
            ("supplier", "Supplier"),
            ("category", "Category"),
        ],
        string="Scope",
    )
    key = fields.Char(
        string="Key",
        help="Unique identifier for this policy.",
    )
    rules_json = fields.Text(
        string="Rules (JSON)",
        help="JSON-encoded rules for this policy.",
    )
    version = fields.Integer(
        string="Version",
        default=1,
    )
    active_from = fields.Date(
        string="Active From",
    )
    active_to = fields.Date(
        string="Active To",
    )
    is_active = fields.Boolean(
        string="Active",
        default=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
    )
