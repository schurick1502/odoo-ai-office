{
    "name": "AI Office \u2013 Steuerb\u00fcro Framework",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "AI-powered accounting office framework with case management, suggestions, audit trail, and policy engine.",
    "description": """
AI Office - Steuerbuero Framework
==================================
Provides a structured workflow for AI-assisted accounting:
- Case management with state machine
- AI suggestions with confidence scoring
- Immutable audit trail
- Configurable policy engine
    """,
    "author": "One Million Digital UG",
    "website": "https://onemillion-digital.de",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
        "mail",
        "fetchmail",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/seed_policies.xml",
        "data/mail_alias.xml",
        "views/ai_case_views.xml",
        "views/ai_suggestion_views.xml",
        "wizard/audit_log_export_views.xml",
        "wizard/datev_export_views.xml",
        "wizard/tax_report_views.xml",
        "views/ai_audit_log_views.xml",
        "views/ai_policy_views.xml",
        "views/menu.xml",
    ],
    "application": True,
    "installable": True,
}
