import json
import logging
import uuid

import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import email_split

_logger = logging.getLogger(__name__)


class AiCase(models.Model):
    _name = "account.ai.case"
    _description = "AI Office Case"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    _mail_post_access = "read"

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

    ALLOWED_ATTACHMENT_MIMETYPES = {
        "application/pdf",
        "application/xml",
        "text/xml",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/bmp",
    }

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

    # ── Audit ───────────────────────────────────────────────────────────

    def _log_audit(self, action, before_vals=None, after_vals=None,
                   actor_type="user", actor=None):
        """Create an audit log entry for this case."""
        self.ensure_one()
        self.env["account.ai.audit_log"].sudo().create({
            "case_id": self.id,
            "actor_type": actor_type,
            "actor": actor or self.env.user.name,
            "action": action,
            "before_json": json.dumps(before_vals) if before_vals else False,
            "after_json": json.dumps(after_vals) if after_vals else False,
        })

    # ── Email Intake ────────────────────────────────────────────────────

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Create a new AI case from an incoming email.

        Called by the mail system when an email arrives at the configured
        alias. Extracts attachments, matches/creates a partner from the
        sender email, and logs an audit entry.
        """
        defaults = dict(custom_values or {})
        # Create the case via super() (handles mail.thread logic)
        case = super().message_new(msg_dict, custom_values=defaults)

        # Find or create partner from sender email
        email_from = msg_dict.get("email_from", "")
        if email_from:
            parsed = email_split(email_from)
            email_addr = parsed[0] if parsed else ""
            # Extract display name from "Name <email>" format
            display_name = email_from.split("<")[0].strip().strip('"') if "<" in email_from else ""
            partner = case._get_or_create_partner(email_addr, name=display_name)
            if partner:
                case.partner_id = partner

        # Filter and link document attachments from the email message
        if case.message_ids:
            all_attachments = case.message_ids[0].attachment_ids
            valid_attachments = case._filter_attachments(all_attachments)
            if valid_attachments:
                case.document_ids = [(6, 0, valid_attachments.ids)]

        # Audit log: agent-type entry for automated intake
        case._log_audit(
            "email_intake",
            after_vals={
                "state": "new",
                "partner_id": case.partner_id.id or None,
                "partner_name": case.partner_id.name or "",
                "document_count": len(case.document_ids),
                "email_from": email_from,
            },
            actor_type="agent",
            actor="mail_intake",
        )

        return case

    def _get_or_create_partner(self, email, name=None):
        """Find existing partner by email or create a new supplier.

        Returns a res.partner recordset (may be empty if email is falsy).
        """
        if not email:
            return self.env["res.partner"]

        email = email.strip().lower()
        partner = self.env["res.partner"].search([
            ("email", "=ilike", email),
        ], limit=1)

        if not partner:
            partner = self.env["res.partner"].create({
                "name": name or email,
                "email": email,
                "supplier_rank": 1,
                "company_id": self.env.company.id,
            })

        return partner

    def _filter_attachments(self, attachment_ids):
        """Filter attachments to only accepted MIME types."""
        return attachment_ids.filtered(
            lambda att: att.mimetype in self.ALLOWED_ATTACHMENT_MIMETYPES
        )

    # ── State Transitions ───────────────────────────────────────────────

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
        """Transition from proposed to approved. Requires approver group and GoBD validation."""
        if not self.env.user.has_group("account_ai_office.ai_office_approver"):
            raise UserError(_("Only users with the AI Office Approver role can approve cases."))
        for record in self:
            if record.state != "proposed":
                raise UserError(
                    _("Case %s cannot be approved from state '%s'. Must be 'Proposed'.")
                    % (record.name, record.state)
                )
            record._validate_gobd()
            before = {"state": record.state}
            record.state = "approved"
            record._log_audit("approve", before_vals=before, after_vals={"state": "approved"})

    def action_post(self):
        """Transition from approved to posted. Creates account.move. Requires approver group."""
        if not self.env.user.has_group("account_ai_office.ai_office_approver"):
            raise UserError(_("Only users with the AI Office Approver role can post cases."))
        for record in self:
            if record.state != "approved":
                raise UserError(
                    _("Case %s cannot be posted from state '%s'. Must be 'Approved'.")
                    % (record.name, record.state)
                )
            move = record._create_move_from_suggestion()
            before = {"state": record.state}
            record.state = "posted"
            record._log_audit(
                "post",
                before_vals=before,
                after_vals={
                    "state": "posted",
                    "move_id": move.id,
                    "move_name": move.name,
                },
            )

    def _create_move_from_suggestion(self):
        """Create an account.move from the first accounting_entry suggestion.

        Returns the created account.move record.
        Raises UserError if no suitable suggestion is found or accounts cannot be resolved.
        """
        self.ensure_one()
        suggestion = self.suggestion_ids.filtered(
            lambda s: s.suggestion_type == "accounting_entry"
        )[:1]
        if not suggestion:
            raise UserError(
                _("Case %s has no accounting entry suggestion to post.") % self.name
            )

        try:
            payload = json.loads(suggestion.payload_json or "{}")
        except (json.JSONDecodeError, TypeError):
            raise UserError(_("Invalid suggestion payload for case %s.") % self.name)

        lines = payload.get("lines", [])
        if not lines:
            raise UserError(_("Suggestion for case %s has no booking lines.") % self.name)

        # Determine journal: purchase journal of the company
        journal = self.env["account.journal"].search([
            ("type", "=", "purchase"),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not journal:
            journal = self.env["account.journal"].search([
                ("company_id", "=", self.company_id.id),
            ], limit=1)
        if not journal:
            raise UserError(_("No journal found for company %s.") % self.company_id.name)

        # Determine date from enrichment context or today
        enrichment = self._get_enrichment_context()
        move_date = enrichment.get("invoice_date") or fields.Date.context_today(self)

        # Build move lines
        move_lines = []
        for line in lines:
            account_code = line.get("account", "")
            account = self.env["account.account"].search([
                ("code", "=", account_code),
                ("company_id", "=", self.company_id.id),
            ], limit=1)
            if not account:
                raise UserError(
                    _("Account '%s' not found for company %s.")
                    % (account_code, self.company_id.name)
                )
            move_lines.append((0, 0, {
                "account_id": account.id,
                "name": line.get("description", ""),
                "debit": line.get("debit", 0.0),
                "credit": line.get("credit", 0.0),
                "partner_id": self.partner_id.id or False,
            }))

        move = self.env["account.move"].create({
            "journal_id": journal.id,
            "date": move_date,
            "ref": self.name,
            "partner_id": self.partner_id.id or False,
            "line_ids": move_lines,
            "move_type": "entry",
        })
        self.move_id = move
        return move

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

    # ── GoBD Validation ────────────────────────────────────────────────

    def _get_policy_thresholds(self):
        """Extract confidence and risk thresholds from active policies."""
        self.ensure_one()
        policies = self._get_active_policies()
        thresholds = {
            "confidence_threshold": 0.8,
            "risk_score_max": 0.3,
        }
        for policy in policies:
            rules = policy.get("rules", {})
            if "confidence_threshold" in rules:
                thresholds["confidence_threshold"] = rules["confidence_threshold"]
            if "risk_score_max" in rules:
                thresholds["risk_score_max"] = rules["risk_score_max"]
        return thresholds

    def _validate_gobd(self):
        """Run GoBD validation checks on the case before approval.

        Raises UserError with detailed message on failure.
        """
        self.ensure_one()
        errors = []

        suggestion = self.suggestion_ids.filtered(
            lambda s: s.suggestion_type == "accounting_entry"
        )[:1]
        if not suggestion:
            raise UserError(
                _("GoBD validation failed for case %s: No accounting entry suggestion found.")
                % self.name
            )

        try:
            payload = json.loads(suggestion.payload_json or "{}")
        except (json.JSONDecodeError, TypeError):
            raise UserError(
                _("GoBD validation failed for case %s: Invalid suggestion payload.") % self.name
            )

        lines = payload.get("lines", [])
        if not lines:
            errors.append(_("No booking lines in suggestion."))

        has_verbindlichkeiten = False
        for i, line in enumerate(lines):
            if not line.get("account"):
                errors.append(_("Line %d: missing account code.") % (i + 1))
            debit = line.get("debit", 0.0)
            credit = line.get("credit", 0.0)
            if debit <= 0 and credit <= 0:
                errors.append(_("Line %d: debit or credit must be > 0.") % (i + 1))
            if not line.get("description"):
                errors.append(_("Line %d: missing description (GoBD requires Buchungstext).") % (i + 1))
            if line.get("account") == "1600":
                has_verbindlichkeiten = True

        total_debit = sum(line.get("debit", 0.0) for line in lines)
        total_credit = sum(line.get("credit", 0.0) for line in lines)
        if abs(total_debit - total_credit) > 0.01:
            errors.append(
                _("Entry not balanced: debit=%.2f, credit=%.2f.") % (total_debit, total_credit)
            )

        enrichment = self._get_enrichment_context()
        move_date_str = enrichment.get("invoice_date")
        if move_date_str:
            try:
                move_date = fields.Date.from_string(move_date_str)
                today = fields.Date.context_today(self)
                if move_date > today:
                    errors.append(_("Invoice date %s is in the future.") % move_date_str)
            except (ValueError, TypeError):
                pass

        if has_verbindlichkeiten and not self.partner_id:
            errors.append(
                _("Partner is required for Verbindlichkeiten bookings (account 1600).")
            )

        thresholds = self._get_policy_thresholds()
        if suggestion.confidence < thresholds["confidence_threshold"]:
            errors.append(
                _("Confidence %.2f is below the required threshold %.2f.")
                % (suggestion.confidence, thresholds["confidence_threshold"])
            )
        if suggestion.risk_score > thresholds["risk_score_max"]:
            errors.append(
                _("Risk score %.2f exceeds the maximum allowed %.2f.")
                % (suggestion.risk_score, thresholds["risk_score_max"])
            )

        if errors:
            error_list = "\n".join("- %s" % e for e in errors)
            raise UserError(
                _("GoBD validation failed for case %s:\n\n%s") % (self.name, error_list)
            )

    # ── Service Integration ─────────────────────────────────────────────

    def _get_enrichment_context(self):
        """Extract enrichment data from existing suggestions for orchestration context."""
        enrichment_data = {}
        for suggestion in self.suggestion_ids.filtered(lambda s: s.suggestion_type == "enrichment"):
            try:
                payload = json.loads(suggestion.payload_json or "{}")
                field = payload.get("field", "")
                value = payload.get("value", "")
                if field and value:
                    enrichment_data[field] = value
            except (json.JSONDecodeError, TypeError):
                continue
        return enrichment_data

    def _get_active_policies(self):
        """Load active policies relevant to this case for service context."""
        domain = [
            ("is_active", "=", True),
            "|",
            ("company_id", "=", self.company_id.id),
            ("company_id", "=", False),
        ]
        policies = self.env["account.ai.policy"].sudo().search(domain)
        result = []
        for policy in policies:
            try:
                rules = json.loads(policy.rules_json or "{}")
            except (json.JSONDecodeError, TypeError):
                rules = {}
            result.append({
                "scope": policy.scope,
                "key": policy.key,
                "rules": rules,
            })
        return result

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
                        **self._get_enrichment_context(),
                        "partner_id": self.partner_id.id or None,
                        "partner_name": self.partner_id.name or "",
                        "period": self.period or "",
                        "company_id": self.company_id.id,
                        "policies": self._get_active_policies(),
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

    def action_enrich(self):
        """Call the AI Office Service to enrich this case with document metadata.

        Sends document metadata to /v1/enrich and creates enrichment-type
        suggestions from the response. Transitions state from 'new' to 'enriched'.
        """
        self.ensure_one()
        if self.state != "new":
            raise UserError(
                _("Case %s cannot be enriched from state '%s'. Must be 'New'.")
                % (self.name, self.state)
            )

        service_url = self.env["ir.config_parameter"].sudo().get_param(
            "ai_office.service_url", "http://ai_office_service:8100"
        )
        request_id = str(uuid.uuid4())

        documents = []
        for doc in self.document_ids:
            documents.append({
                "filename": doc.name or "",
                "mimetype": doc.mimetype or "",
                "size_bytes": doc.file_size or 0,
            })

        try:
            response = requests.post(
                f"{service_url}/v1/enrich",
                json={
                    "case_id": self.id,
                    "request_id": request_id,
                    "documents": documents,
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

        for suggestion in data.get("suggestions", []):
            self.env["account.ai.suggestion"].create({
                "case_id": self.id,
                "suggestion_type": "enrichment",
                "payload_json": json.dumps({
                    "field": suggestion.get("field", ""),
                    "value": suggestion.get("value", ""),
                }),
                "confidence": suggestion.get("confidence", 0.0),
                "risk_score": 0.0,
                "explanation_md": "Extracted `%s` = `%s` (source: %s)" % (
                    suggestion.get("field", ""),
                    suggestion.get("value", ""),
                    suggestion.get("source", "unknown"),
                ),
                "requires_human": True,
                "agent_name": "enrichment_agent",
                "request_id": request_id,
            })

        before = {"state": self.state, "suggestion_count": self.suggestion_count}
        self.state = "enriched"
        self._log_audit(
            "enrich",
            before_vals=before,
            after_vals={
                "state": "enriched",
                "enrichment_suggestions": len(data.get("suggestions", [])),
                "request_id": request_id,
            },
        )

    # ── OPOS (Open Item Reconciliation) ──────────────────────────────

    def _get_open_lines(self):
        """Fetch unreconciled move lines for the case's partner on payable/receivable accounts."""
        self.ensure_one()
        if not self.partner_id:
            return []

        domain = [
            ("partner_id", "=", self.partner_id.id),
            ("reconciled", "=", False),
            ("amount_residual", "!=", 0),
            ("company_id", "=", self.company_id.id),
            ("account_id.account_type", "in", ["liability_payable", "asset_receivable"]),
        ]
        move_lines = self.env["account.move.line"].search(domain)
        result = []
        for ml in move_lines:
            result.append({
                "id": ml.id,
                "date": str(ml.date),
                "ref": ml.ref or ml.move_id.ref or "",
                "name": ml.name or "",
                "balance": ml.balance,
                "amount_residual": ml.amount_residual,
                "account_code": ml.account_id.code,
                "move_name": ml.move_id.name or "",
            })
        return result

    def action_run_opos(self):
        """Call the AI Office Service to find matching open items for reconciliation."""
        self.ensure_one()
        if self.state != "posted":
            raise UserError(
                _("OPOS can only be run on cases in 'Posted' state.")
            )
        if not self.move_id:
            raise UserError(
                _("Case %s has no journal entry. Post the case first.") % self.name
            )

        open_lines = self._get_open_lines()
        if not open_lines:
            raise UserError(
                _("No open items found for partner %s.") % (self.partner_id.name or "unknown")
            )

        service_url = self.env["ir.config_parameter"].sudo().get_param(
            "ai_office.service_url", "http://ai_office_service:8100"
        )
        request_id = str(uuid.uuid4())

        try:
            response = requests.post(
                f"{service_url}/v1/opos/match",
                json={
                    "case_id": self.id,
                    "request_id": request_id,
                    "context": {
                        "open_lines": open_lines,
                        "partner_id": self.partner_id.id or None,
                        "partner_name": self.partner_id.name or "",
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

        for suggestion in data.get("suggestions", []):
            self.env["account.ai.suggestion"].create({
                "case_id": self.id,
                "suggestion_type": suggestion.get("suggestion_type", "reconciliation"),
                "payload_json": json.dumps(suggestion.get("payload", {})),
                "confidence": suggestion.get("confidence", 0.0),
                "risk_score": suggestion.get("risk_score", 0.0),
                "explanation_md": suggestion.get("explanation", ""),
                "requires_human": suggestion.get("requires_human", True),
                "agent_name": suggestion.get("agent_name", ""),
                "request_id": request_id,
            })

        self._log_audit(
            "opos_match",
            before_vals={"suggestion_count": self.suggestion_count},
            after_vals={
                "suggestions_added": len(data.get("suggestions", [])),
                "open_lines_sent": len(open_lines),
                "request_id": request_id,
            },
        )

    def action_apply_reconciliation(self):
        """Apply reconciliation suggestions using Odoo's standard reconcile() API."""
        if not self.env.user.has_group("account_ai_office.ai_office_approver"):
            raise UserError(
                _("Only users with the AI Office Approver role can apply reconciliation.")
            )
        self.ensure_one()
        if self.state != "posted":
            raise UserError(
                _("Reconciliation can only be applied on cases in 'Posted' state.")
            )

        recon_suggestions = self.suggestion_ids.filtered(
            lambda s: s.suggestion_type == "reconciliation"
        )
        if not recon_suggestions:
            raise UserError(
                _("Case %s has no reconciliation suggestions. Run OPOS first.") % self.name
            )

        applied_count = 0
        errors = []
        for suggestion in recon_suggestions:
            try:
                payload = json.loads(suggestion.payload_json or "{}")
            except (json.JSONDecodeError, TypeError):
                errors.append(_("Invalid reconciliation payload."))
                continue

            for match in payload.get("matches", []):
                debit_line_id = match.get("debit_line_id")
                credit_line_id = match.get("credit_line_id")
                if not debit_line_id or not credit_line_id:
                    errors.append(_("Match missing line IDs."))
                    continue

                lines = self.env["account.move.line"].browse(
                    [debit_line_id, credit_line_id]
                ).exists()
                if len(lines) != 2:
                    errors.append(
                        _("Move lines %s/%s not found.") % (debit_line_id, credit_line_id)
                    )
                    continue

                if all(rec.reconciled for rec in lines):
                    continue

                try:
                    lines.reconcile()
                    applied_count += 1
                except Exception as e:
                    errors.append(
                        _("Reconciliation failed for lines %s/%s: %s")
                        % (debit_line_id, credit_line_id, str(e))
                    )

        self._log_audit(
            "reconciliation_applied",
            before_vals={"reconciliation_suggestions": len(recon_suggestions)},
            after_vals={
                "applied_count": applied_count,
                "errors": errors,
            },
        )

        if errors:
            raise UserError(
                _("Reconciliation completed with errors:\n\n%s")
                % "\n".join("- %s" % e for e in errors)
            )
