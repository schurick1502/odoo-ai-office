# Environment Variable Reference

Copy `.env.example` to `.env` and set all required values before deployment.

## Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_DB` | PostgreSQL database name | `odoo_ai_office` |
| `POSTGRES_USER` | PostgreSQL user | `odoo` |
| `POSTGRES_PASSWORD` | PostgreSQL password (min 16 chars) | `<generated>` |
| `ODOO_DB` | Odoo database name (must match POSTGRES_DB) | `odoo_ai_office` |
| `ODOO_ADMIN_PASSWD` | Odoo admin master password | `<generated>` |

## Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ODOO_PORT` | Host port for Odoo | `8069` |
| `AI_SERVICE_HOST` | AI service hostname (Docker DNS) | `ai_office_service` |
| `AI_SERVICE_PORT` | AI service port | `8100` |
| `AI_SERVICE_URL` | Full service URL | `http://ai_office_service:8100` |
| `SERVICE_VERSION` | Docker image tag for AI service | `latest` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FORMAT` | Log format | `json` |

### LOG_LEVEL values

`DEBUG`, `INFO`, `WARNING`, `ERROR`

### LOG_FORMAT values

- `json` — Structured JSON output (recommended for production, machine-parseable)
- `console` — Colored human-readable output (recommended for development)

## Security Notes

- Never commit `.env` to version control (it is in `.gitignore`)
- Generate passwords with: `openssl rand -base64 24`
- For production, consider Docker secrets or HashiCorp Vault
- Rotate `POSTGRES_PASSWORD` and `ODOO_ADMIN_PASSWD` periodically
- The `compose.prod.yml` will fail to start if required variables are missing
