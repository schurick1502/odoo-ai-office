"""XML-RPC client for Odoo's account_ai_office module."""

import json
import os
import xmlrpc.client


class OdooAiOfficeClient:
    """Odoo XML-RPC client for account.ai.case and related models."""

    def __init__(
        self,
        url: str | None = None,
        db: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        self.url = (url or os.getenv("ODOO_URL", "http://localhost:8069")).rstrip("/")
        self.db = db or os.getenv("ODOO_DB", "odoo_ai_office")
        self.username = username or os.getenv("ODOO_USERNAME", "admin")
        self.password = password or os.getenv("ODOO_PASSWORD", "admin")
        self._uid: int | None = None
        self._common: xmlrpc.client.ServerProxy | None = None
        self._object: xmlrpc.client.ServerProxy | None = None

    def _get_common(self) -> xmlrpc.client.ServerProxy:
        if self._common is None:
            self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        return self._common

    def _get_object(self) -> xmlrpc.client.ServerProxy:
        if self._object is None:
            self._object = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return self._object

    def authenticate(self) -> int:
        """Authenticate and return uid."""
        if self._uid is None:
            self._uid = self._get_common().authenticate(
                self.db, self.username, self.password, {}
            )
        if not self._uid:
            raise ConnectionError(
                f"Odoo authentication failed for {self.username}@{self.url}/{self.db}"
            )
        return self._uid

    def _execute(self, model: str, method: str, *args, **kwargs):
        """Execute an Odoo RPC call."""
        uid = self.authenticate()
        return self._get_object().execute_kw(
            self.db, uid, self.password, model, method, *args, **kwargs
        )

    def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
    ) -> list[dict]:
        kwargs: dict = {}
        if fields:
            kwargs["fields"] = fields
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if order:
            kwargs["order"] = order
        return self._execute(model, "search_read", [domain], kwargs)

    def create(self, model: str, vals: dict) -> int:
        return self._execute(model, "create", [vals])

    def write(self, model: str, record_id: int, vals: dict) -> bool:
        return self._execute(model, "write", [[record_id], vals])

    # ── Case Operations ─────────────────────────────────────

    def list_cases(
        self,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        domain = []
        if state:
            domain.append(("state", "=", state))
        return self.search_read(
            "account.ai.case",
            domain,
            fields=["name", "state", "partner_id", "period", "suggestion_count", "create_date"],
            limit=limit,
            offset=offset,
            order="create_date desc",
        )

    def get_case(self, case_id: int) -> dict:
        results = self.search_read(
            "account.ai.case",
            [("id", "=", case_id)],
            fields=[
                "name", "state", "partner_id", "period", "company_id",
                "source_model", "source_id", "move_id", "suggestion_count",
                "create_date",
            ],
        )
        if not results:
            raise ValueError(f"Case {case_id} not found")
        return results[0]

    def create_case(self, vals: dict) -> int:
        """Create an AI case. Handles partner matching if partner_name provided."""
        create_vals = {}
        if vals.get("period"):
            create_vals["period"] = vals["period"]
        if vals.get("source_model"):
            create_vals["source_model"] = vals["source_model"]
        if vals.get("source_id"):
            create_vals["source_id"] = vals["source_id"]

        # Match or create partner
        partner_name = vals.get("partner_name")
        partner_email = vals.get("partner_email")
        if partner_name or partner_email:
            partner_id = self._find_or_create_partner(partner_name, partner_email)
            if partner_id:
                create_vals["partner_id"] = partner_id

        return self.create("account.ai.case", create_vals)

    def _find_or_create_partner(
        self,
        name: str | None = None,
        email: str | None = None,
    ) -> int | None:
        """Find partner by email or name, create if not found."""
        if email:
            partners = self.search_read(
                "res.partner",
                [("email", "=ilike", email)],
                fields=["id"],
                limit=1,
            )
            if partners:
                return partners[0]["id"]

        if name:
            partners = self.search_read(
                "res.partner",
                [("name", "=ilike", name)],
                fields=["id"],
                limit=1,
            )
            if partners:
                return partners[0]["id"]

            # Create new supplier
            return self.create("res.partner", {
                "name": name,
                "email": email or "",
                "supplier_rank": 1,
            })
        return None

    def add_suggestion(self, case_id: int, vals: dict) -> int:
        create_vals = {
            "case_id": case_id,
            "suggestion_type": vals.get("suggestion_type", "accounting_entry"),
            "payload_json": json.dumps(vals.get("payload", {})),
            "confidence": vals.get("confidence", 0.0),
            "risk_score": vals.get("risk_score", 0.0),
            "explanation_md": vals.get("explanation", ""),
            "requires_human": vals.get("requires_human", True),
            "agent_name": vals.get("agent_name", ""),
        }
        return self.create("account.ai.suggestion", create_vals)

    def action_propose(self, case_id: int) -> bool:
        return self._execute("account.ai.case", "action_propose", [[case_id]])

    def action_approve(self, case_id: int) -> bool:
        return self._execute("account.ai.case", "action_approve", [[case_id]])

    def action_post(self, case_id: int) -> bool:
        return self._execute("account.ai.case", "action_post", [[case_id]])

    def action_export(self, case_id: int) -> bool:
        return self._execute("account.ai.case", "action_export", [[case_id]])

    # ── Suggestion & Audit Operations ───────────────────────

    def get_suggestions(self, case_id: int) -> list[dict]:
        return self.search_read(
            "account.ai.suggestion",
            [("case_id", "=", case_id)],
            fields=[
                "suggestion_type", "payload_json", "confidence", "risk_score",
                "explanation_md", "requires_human", "agent_name", "create_date",
            ],
            order="create_date desc",
        )

    def search_partners(self, query: str) -> list[dict]:
        return self.search_read(
            "res.partner",
            ["|", ("name", "ilike", query), ("email", "ilike", query)],
            fields=["name", "email", "supplier_rank"],
            limit=20,
        )

    def list_audit_logs(self, case_id: int) -> list[dict]:
        return self.search_read(
            "account.ai.audit_log",
            [("case_id", "=", case_id)],
            fields=[
                "actor_type", "actor", "action",
                "before_json", "after_json", "create_date",
            ],
            order="create_date asc",
        )

    def health(self) -> dict:
        """Test Odoo connectivity."""
        try:
            version = self._get_common().version()
            uid = self.authenticate()
            return {
                "status": "ok",
                "odoo_version": version.get("server_version", "unknown"),
                "uid": uid,
                "database": self.db,
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    def case_exists(self, source_model: str, source_id: int) -> bool:
        """Check if a case with the given source already exists (deduplication)."""
        results = self.search_read(
            "account.ai.case",
            [("source_model", "=", source_model), ("source_id", "=", source_id)],
            fields=["id"],
            limit=1,
        )
        return len(results) > 0
