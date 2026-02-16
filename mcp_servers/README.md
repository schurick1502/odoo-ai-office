# MCP Servers – DocumentFlow ↔ Odoo Bridge

Two [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) servers that bridge **DocumentFlow** (document processing) and **Odoo AI Office** (accounting), plus an automated sync daemon.

## Architecture

```
DocumentFlow (:8000)                    Odoo (:8069)
    REST API                              XML-RPC
       ↕                                    ↕
[DocFlow MCP Server]  ← bridge →  [Odoo AI Office MCP Server]
    (STDIO)                            (STDIO)
                   ↘        ↙
               [Bridge Sync Script]
               (cron / daemon)
```

## Setup

```bash
cd mcp_servers
pip install ".[dev]"
```

## MCP Servers

### DocumentFlow Server

Exposes 8 tools: `docflow_list_jobs`, `docflow_get_job`, `docflow_get_bookings`, `docflow_get_positions`, `docflow_approve_job`, `docflow_export_datev`, `docflow_search_jobs`, `docflow_health`.

```bash
# Run standalone
DOCFLOW_URL=http://localhost:8000 DOCFLOW_TOKEN=your-jwt \
  python -m mcp_servers.docflow.server
```

### Odoo AI Office Server

Exposes 12 tools: `odoo_list_cases`, `odoo_get_case`, `odoo_create_case`, `odoo_add_suggestion`, `odoo_propose_case`, `odoo_approve_case`, `odoo_post_case`, `odoo_export_case`, `odoo_get_suggestions`, `odoo_search_partners`, `odoo_list_audit_logs`, `odoo_health`.

```bash
# Run standalone
ODOO_URL=http://localhost:8069 ODOO_DB=odoo_ai_office ODOO_USERNAME=admin ODOO_PASSWORD=secret \
  python -m mcp_servers.odoo_bridge.server
```

### MCP Inspector (interactive testing)

```bash
npx @modelcontextprotocol/inspector python -m mcp_servers.docflow.server
npx @modelcontextprotocol/inspector python -m mcp_servers.odoo_bridge.server
```

## Bridge Sync

Automatically transfers approved DocumentFlow jobs to Odoo AI cases with enrichment and accounting entry suggestions.

```bash
# Single sync run
python -m mcp_servers.bridge.sync --once

# Daemon mode (polls every 60s)
python -m mcp_servers.bridge.sync --daemon

# Dry run (no writes to Odoo)
python -m mcp_servers.bridge.sync --once --dry-run
```

## Claude Desktop Configuration

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "docflow": {
      "command": "python",
      "args": ["-m", "mcp_servers.docflow.server"],
      "cwd": "/path/to/odoo-ai-office",
      "env": {
        "DOCFLOW_URL": "http://localhost:8000",
        "DOCFLOW_USERNAME": "admin",
        "DOCFLOW_PASSWORD": "your-password"
      }
    },
    "odoo-ai-office": {
      "command": "python",
      "args": ["-m", "mcp_servers.odoo_bridge.server"],
      "cwd": "/path/to/odoo-ai-office",
      "env": {
        "ODOO_URL": "http://localhost:8069",
        "ODOO_DB": "odoo_ai_office",
        "ODOO_USERNAME": "admin",
        "ODOO_PASSWORD": "your-password"
      }
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCFLOW_URL` | `http://localhost:8000` | DocumentFlow API URL |
| `DOCFLOW_USERNAME` | — | DocumentFlow username |
| `DOCFLOW_PASSWORD` | — | DocumentFlow password |
| `DOCFLOW_TOKEN` | — | Pre-existing JWT (alternative to user/pass) |
| `ODOO_URL` | `http://localhost:8069` | Odoo URL |
| `ODOO_DB` | `odoo_ai_office` | Odoo database name |
| `ODOO_USERNAME` | `admin` | Odoo username |
| `ODOO_PASSWORD` | `admin` | Odoo password |
| `BRIDGE_SYNC_INTERVAL` | `60` | Seconds between sync cycles (daemon mode) |
| `BRIDGE_SYNC_STATUSES` | `approved` | Comma-separated DocumentFlow statuses to sync |
| `BRIDGE_DRY_RUN` | `false` | Set to `true` for testing without writes |

## Tests

```bash
cd mcp_servers
pytest -v --tb=short
```
