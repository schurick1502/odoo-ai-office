import json
import logging
import uuid

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AiCase(models.Model):
    _name = "account.ai.case"
    _description = "AI Office Case"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    STATES = [
        ("new", "New"),
        ("enriched", "Enriched"),
        ("proposed", "Proposed"),
        ("approved", "Approved"),
        ("posted", "Posted"),
        ("exported", "Exported"),
        ("needs_attention", "Needs Attention"),
        ("failed", "Failed"),
    ]

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code("account.ai.case") or "New",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        selection=STATES,
        string="State",
        default="new",
        required=True,
        tracking=True,
        copy=False,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
    )
    source_model = fields.Char(
        string="Source Model",
    )
    source_id = fields.Integer(
        string="Source ID",
    )
    document_ids = fields.Many2many(
        "ir.attachment",
        string="Documents",
    )
    period = fields.Char(
        string="Period",
        help="Accounting period, e.g. 2024-01",
    )
    suggestion_ids = fields.One2many(
        "account.ai.suggestion",
        "case_id",
        string="Suggestions",
    )
    audit_log_ids = fields.One2many(
        "account.ai.audit_log",
        "case_id",
        string="Audit Logs",
    )
    suggestion_count = fields.Integer(
        string="Suggestions",
        compute="_compute_suggestion_count",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
    )

    @api.depends("suggestion_ids")
    def _compute_suggestion_count(self):
        for record in self:
            record.suggestion_count = len(record.suggestion_ids)

    def _log_audit(self, action, before_vals=None, after_vals=None):
        """Create an audit log entry for this case."""
        self.ensure_one()
        self.env["account.ai.audit_log"].sudo().create({
            "case_id": self.id,
            "actor_type": "user",
            "actor": self.env.user.name,
            "action": action,
            "before_json": json.dumps(before_vals) if before_vals else False,
            "after_json": json.dumps(after_vals) if after_vals else False,
        })

    def action_propose(self):
        """Transition from new/enriched to proposed."""
        for record in self:
            if record.state not in ("new", "enriched"):
                raise UserError(
                    _("Case %s cannot be proposed from state '%s'. Must be 'New' or 'Enriched'.")
                    % (record.name, record.state)
                )
            before = {"state": record.state}
            record.state = "proposed"
            record._log_audit("propose", before_vals=before, after_vals={"state": "proposed"})

    def action_approve(self):
        """Transition from proposed to approved. Requires approver group."""
        if not self.env.user.has_group("account_ai_office.ai_office_approver"):
            raise UserError(_("Only users with the AI Office Approver role can approve cases."))
        for record in self:
            if record.state != "proposed":
                raise UserError(
                    _("Case %s cannot be approved from state '%s'. Must be 'Proposed'.")
                    % (record.name, record.state)
                )
            before = {"state": record.state}
            record.state = "approved"
            record._log_audit("approve", before_vals=before, after_vals={"state": "approved"})

    def action_post(self):
        """Transition from approved to posted. Requires approver group."""
        if not self.env.user.has_group("account_ai_office.ai_office_approver"):
            raise UserError(_("Only users with the AI Office Approver role can post cases."))
        for record in self:
            if record.state != "approved":
                raise UserError(
                    _("Case %s cannot be posted from state '%s'. Must be 'Approved'.")
                    % (record.name, record.state)
                )
            before = {"state": record.state}
            record.state = "posted"
            record._log_audit("post", before_vals=before, after_vals={"state": "posted"})

    def action_export(self):
        """Transition from posted to exported."""
        for record in self:
            if record.state != "posted":
                raise UserError(
                    _("Case %s cannot be exported from state '%s'. Must be 'Posted'.")
                    % (record.name, record.state)
                )
            before = {"state": record.state}
            record.state = "exported"
            record._log_audit("export", before_vals=before, after_vals={"state": "exported"})

    def action_reset_to_new(self):
        """Reset from needs_attention or failed back to new."""
        for record in self:
            if record.state not in ("needs_attention", "failed"):
                raise UserError(
                    _("Case %s cannot be reset from state '%s'. Must be 'Needs Attention' or 'Failed'.")
                    % (record.name, record.state)
                )
            before = {"state": record.state}
            record.state = "new"
            record._log_audit("reset_to_new", before_vals=before, after_vals={"state": "new"})

    def action_needs_attention(self):
        """Flag case as needing attention from any state."""
        for record in self:
            before = {"state": record.state}
            record.state = "needs_attention"
            record._log_audit("needs_attention", before_vals=before, after_vals={"state": "needs_attention"})

    def action_run_orchestrator(self):
        """Call the AI Office Service to generate suggestions for this case."""
        self.ensure_one()
        if self.state not in ("new", "enriched"):
            raise UserError(
                _("AI orchestration can only be run on cases in 'New' or 'Enriched' state.")
            )

        service_url = self.env["ir.config_parameter"].sudo().get_param(
            "ai_office.service_url", "http://ai_office_service:8100"
        )
        request_id = str(uuid.uuid4())

        try:
            response = requests.post(
                f"{service_url}/v1/orchestrate",
                json={
                    "case_id": self.id,
                    "request_id": request_id,
                    "context": {
                        "partner_id": self.partner_id.id or None,
                        "partner_name": self.partner_id.name or "",
                        "period": self.period or "",
                        "company_id": self.company_id.id,
                    },
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.ConnectionError:
            raise UserError(_("Cannot connect to AI Office Service at %s") % service_url)
        except requests.exceptions.Timeout:
            raise UserError(_("AI Office Service timed out."))
        except requests.exceptions.RequestException as e:
            raise UserError(_("AI Office Service error: %s") % str(e))

        # Write suggestions from response
        for suggestion in data.get("suggestions", []):
            self.env["account.ai.suggestion"].create({
                "case_id": self.id,
                "suggestion_type": suggestion.get("suggestion_type", "accounting_entry"),
                "payload_json": json.dumps(suggestion.get("payload", {})),
                "confidence": suggestion.get("confidence", 0.0),
                "risk_score": suggestion.get("risk_score", 0.0),
                "explanation_md": suggestion.get("explanation", ""),
                "requires_human": suggestion.get("requires_human", True),
                "agent_name": suggestion.get("agent_name", ""),
                "request_id": request_id,
            })

        # Log audit entry and transition state
        before = {"state": self.state, "suggestion_count": self.suggestion_count}
        self.state = "proposed"
        self._log_audit(
            "orchestrate",
            before_vals=before,
            after_vals={
                "state": "proposed",
                "suggestions_added": len(data.get("suggestions", [])),
                "request_id": request_id,
            },
        )
