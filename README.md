# Odoo AI Office – Steuerbüro-Framework

AI-powered Accounting Office Framework for Odoo 18. Automates bookkeeping workflows with human-in-the-loop approval for GoBD/audit compliance.

## Architecture

```
┌─────────────┐     REST/JSON      ┌──────────────────┐
│  Odoo 18    │ ◄────────────────► │  AI Office       │
│  Addon      │                    │  Service         │
│             │                    │  (FastAPI)       │
└─────────────┘                    └──────────────────┘
       │                                    │
       ▼                                    ▼
  PostgreSQL                        LLM Providers
```

## Quick Start (Dev)

```bash
cp .env.example .env
# edit .env with your values
docker compose -f compose.dev.yml up -d
```

Odoo: http://localhost:8069
AI Service: http://localhost:8100/health

## Addon: `account_ai_office`

### Models
- `account.ai.case` – Central processing unit (inbox item)
- `account.ai.suggestion` – AI-generated booking suggestions
- `account.ai.audit_log` – Immutable audit trail (GoBD)
- `account.ai.policy` – Configurable rules per company/supplier

### State Machine
```
new → enriched → proposed → approved → posted → exported
                                  ↘ needs_attention
                                  ↘ failed
```

### Security Groups
- **AI Office User** – read/create cases
- **AI Office Approver** – approve & post (human-in-the-loop)
- **AI Office Admin** – manage policies, export audit logs

## Service: `ai_office_service`

FastAPI microservice for AI orchestration.

- `GET /health` – Health check
- `POST /v1/orchestrate` – Run AI pipeline on a case

## Development

```bash
# Run service tests
docker compose -f compose.dev.yml exec ai_office_service pytest

# Run Odoo tests
docker compose -f compose.dev.yml exec odoo odoo --test-enable -d odoo_ai_office -u account_ai_office --stop-after-init
```

## Release

Tag with `vX.Y.Z` to trigger CI build + GHCR push.

## License

MIT
