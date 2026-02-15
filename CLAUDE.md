# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Odoo AI Office – AI-powered accounting office framework for Odoo 18. Two-component architecture: an Odoo addon (`account_ai_office`) communicates via REST/JSON with a FastAPI microservice (`ai_office_service`) that orchestrates AI agents to generate booking suggestions. Human-in-the-loop approval is mandatory (GoBD/audit compliance – no auto-posting).

## Commands

### Development Environment

```bash
cp .env.example .env        # first-time setup
docker compose -f compose.dev.yml up -d
```

- Odoo: http://localhost:8169
- AI Service: http://localhost:8100/health
- PostgreSQL: localhost:5433

### Linting

```bash
ruff check service/
ruff check odoo/addons/account_ai_office/
```

Config: `ruff.toml` – Python 3.12 target, selects E/F/W, ignores E501. Odoo files ignore F401/F811 (XML-generated imports).

### Service Tests (FastAPI, pytest)

```bash
# Inside container
docker compose -f compose.dev.yml exec ai_office_service pytest -v --tb=short

# Or locally (from service/ directory)
cd service && pip install ".[dev]" && pytest -v --tb=short
```

pytest config in `service/pyproject.toml`: `asyncio_mode = "auto"`, `testpaths = ["tests"]`.

### Odoo Addon Tests

```bash
docker compose -f compose.dev.yml exec odoo \
  odoo --test-enable -d odoo_ai_office -u account_ai_office --stop-after-init
```

### Release

Tag with `vX.Y.Z` → GitHub Actions builds and pushes Docker image to GHCR + creates GitHub Release.

## Architecture

```
odoo/addons/account_ai_office/   ← Odoo 18 addon (LGPL-3)
service/                          ← FastAPI microservice (MIT)
  app/main.py                     ← FastAPI app, includes /v1 router
  app/orchestrator/router.py      ← POST /v1/orchestrate endpoint
  app/agents/dummy_agent.py       ← Placeholder agent (returns hardcoded suggestion)
  app/schemas/                    ← Pydantic v2 request/response models
  tests/                          ← pytest + pytest-asyncio tests
```

### Odoo Addon Models

| Model | Purpose |
|-------|---------|
| `account.ai.case` | Central unit – state machine: `new → enriched → proposed → approved → posted → exported` (also `needs_attention`, `failed`) |
| `account.ai.suggestion` | AI-generated booking suggestions linked to a case |
| `account.ai.audit_log` | Immutable GoBD-compliant audit trail – deletion blocked except for superuser |
| `account.ai.policy` | JSON-based rules engine (confidence thresholds, risk limits) per company/supplier |

### Security Groups (hierarchical)

- `ai_office_user` → read/create cases & suggestions
- `ai_office_approver` → inherits user, can approve & post
- `ai_office_admin` → inherits approver, full CRUD on all models

Record rules enforce company-based isolation.

### Key Integration Flow

1. User clicks "Run AI" on a case (`action_run_orchestrator()`)
2. Odoo sends POST to `{AI_SERVICE_URL}/v1/orchestrate` with case context
3. Service runs agent pipeline, returns suggestions
4. Odoo creates `account.ai.suggestion` records + audit log entry
5. Human reviews → approves → posts (state transitions with audit logging)

### Audit Logging Pattern

All state changes call `_log_audit()` which captures before/after state as JSON. The `account.ai.audit_log` model overrides `unlink()` to prevent deletion (GoBD compliance).

## Key Configuration

- Service URL configured via `ir.config_parameter` key `ai_office.service_url` (default: `http://ai_office_service:8100`)
- Auto-generated case sequence: `AIC-%(year)s-#####`
- Dev compose mounts `./service/app` and `./service/tests` for hot-reload
- Dev compose mounts `./odoo/addons` as `/mnt/extra-addons`

## CI Pipeline

GitHub Actions (`.github/workflows/ci.yml`): lint → test-service → build-service (sequential). Triggers on push/PR to main/dev.

## Conventions

- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `chore:` prefix (conventional commits)
- Odoo 18 views use `<list>` not `<tree>`
- XML IDs follow Odoo convention: `view_ai_case_tree`, `action_ai_case_all`, etc.
- Python: formatted with ruff, no line length limit
