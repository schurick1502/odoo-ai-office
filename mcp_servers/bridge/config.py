"""Bridge configuration from environment variables."""

import os
from dataclasses import dataclass, field


@dataclass
class BridgeConfig:
    """Configuration for the DocumentFlow-Odoo bridge sync."""

    # DocumentFlow
    docflow_url: str = ""
    docflow_username: str = ""
    docflow_password: str = ""
    docflow_token: str = ""

    # Odoo
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_username: str = ""
    odoo_password: str = ""

    # Sync
    sync_interval: int = 60
    sync_statuses: list[str] = field(default_factory=lambda: ["approved"])
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        statuses_str = os.getenv("BRIDGE_SYNC_STATUSES", "approved")
        return cls(
            docflow_url=os.getenv("DOCFLOW_URL", "http://localhost:8000"),
            docflow_username=os.getenv("DOCFLOW_USERNAME", ""),
            docflow_password=os.getenv("DOCFLOW_PASSWORD", ""),
            docflow_token=os.getenv("DOCFLOW_TOKEN", ""),
            odoo_url=os.getenv("ODOO_URL", "http://localhost:8069"),
            odoo_db=os.getenv("ODOO_DB", "odoo_ai_office"),
            odoo_username=os.getenv("ODOO_USERNAME", "admin"),
            odoo_password=os.getenv("ODOO_PASSWORD", "admin"),
            sync_interval=int(os.getenv("BRIDGE_SYNC_INTERVAL", "60")),
            sync_statuses=[s.strip() for s in statuses_str.split(",") if s.strip()],
            dry_run=os.getenv("BRIDGE_DRY_RUN", "false").lower() == "true",
        )
