from odoo import models, fields


class AiSuggestion(models.Model):
    _name = "account.ai.suggestion"
    _description = "AI Office Suggestion"
    _order = "create_date desc"

    case_id = fields.Many2one(
        "account.ai.case",
        string="Case",
        required=True,
        ondelete="cascade",
    )
    suggestion_type = fields.Selection(
        [
            ("accounting_entry", "Accounting Entry"),
            ("classification", "Classification"),
            ("enrichment", "Enrichment"),
            ("validation", "Validation"),
            ("reconciliation", "Reconciliation"),
        ],
        string="Type",
    )
    payload_json = fields.Text(
        string="Payload (JSON)",
        help="JSON payload containing the suggestion details.",
    )
    confidence = fields.Float(
        string="Confidence",
        help="Confidence score between 0 and 1.",
    )
    risk_score = fields.Float(
        string="Risk Score",
        help="Risk score between 0 and 1.",
    )
    explanation_md = fields.Text(
        string="Explanation (Markdown)",
        help="Markdown-formatted explanation of the suggestion.",
    )
    requires_human = fields.Boolean(
        string="Requires Human Review",
        default=False,
    )
    agent_name = fields.Char(
        string="Agent Name",
    )
    request_id = fields.Char(
        string="Request ID",
    )
    company_id = fields.Many2one(
        related="case_id.company_id",
        string="Company",
        store=True,
    )
