# Runbook: Operational Procedures

## Health Checks

| Service | URL / Command | Expected |
|---------|--------------|----------|
| Odoo | `curl http://localhost:8069/web/health` | HTTP 200 |
| AI Service | `curl http://localhost:8100/health` | `{"status":"ok"}` |
| AI Metrics | `curl http://localhost:8100/metrics` | Prometheus text |
| PostgreSQL | `docker compose -f compose.prod.yml exec db pg_isready` | "accepting connections" |

## Common Issues and Resolutions

### AI Service returns "degraded" health

**Symptom:** `/health` returns `{"status": "degraded"}`

**Check:**
```bash
docker compose -f compose.prod.yml logs ai_office_service --tail 50
```

**Resolution:** Restart the service:
```bash
docker compose -f compose.prod.yml restart ai_office_service
```

### Odoo cannot connect to AI Service

**Symptom:** "Cannot connect to AI Office Service" error when clicking "Run AI"

**Check:**
```bash
docker compose -f compose.prod.yml exec odoo \
  curl -f http://ai_office_service:8100/health
```

**Resolution:**
1. Verify AI service is running: `docker compose -f compose.prod.yml ps ai_office_service`
2. Check service URL: Settings > Technical > System Parameters > `ai_office.service_url`
3. Should be `http://ai_office_service:8100` (internal Docker DNS)

### Database connection failures

**Symptom:** Services fail to start, logs show "connection refused"

**Check:**
```bash
docker compose -f compose.prod.yml logs db --tail 20
```

**Resolution:**
1. Verify PostgreSQL health: `docker compose -f compose.prod.yml ps db`
2. Check disk space: `df -h`
3. Check resource usage: `docker stats`

### Out of memory (OOM)

**Symptom:** Container killed, `docker inspect` shows `OOMKilled: true`

**Resolution:** Increase memory limits in `compose.prod.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 2G  # increase as needed
```

## Rollback Procedures

### Quick rollback (service only)

```bash
# Pin to previous known-good version
export SERVICE_VERSION=0.2.0
docker compose -f compose.prod.yml up -d ai_office_service
```

### Full rollback

```bash
# 1. Stop all services
docker compose -f compose.prod.yml down

# 2. Checkout previous release tag
git checkout v0.2.0

# 3. Restore database
docker compose -f compose.prod.yml up -d db
sleep 10  # wait for PostgreSQL to start
gunzip < backup_YYYYMMDD.sql.gz | \
  docker compose -f compose.prod.yml exec -T db \
  psql -U $POSTGRES_USER $POSTGRES_DB

# 4. Start all services
docker compose -f compose.prod.yml up -d
```

### Odoo module rollback

```bash
docker compose -f compose.prod.yml exec odoo \
  odoo shell -d $ODOO_DB -c \
  "env['ir.module.module'].search([('name','=','account_ai_office')]).button_immediate_uninstall()"
```

## Log Access

| Service | Command |
|---------|---------|
| Odoo | `docker compose -f compose.prod.yml logs odoo` |
| AI Service | `docker compose -f compose.prod.yml logs ai_office_service` |
| PostgreSQL | `docker compose -f compose.prod.yml logs db` |

AI Service logs are structured JSON when `LOG_FORMAT=json` (default in production).

### Filter logs by level

```bash
docker compose -f compose.prod.yml logs ai_office_service | \
  python3 -c "import sys,json; [print(json.dumps(json.loads(l))) for l in sys.stdin if 'error' in l.lower()]"
```

## Monitoring

### Key Prometheus Metrics

| Metric | Description |
|--------|-------------|
| `http_requests_total` | Total request count by method, path, status |
| `http_request_duration_seconds` | Request latency histogram |
| `http_requests_in_progress` | Currently active requests |

### Recommended Alert Thresholds

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Error rate | > 5% over 5 min | Investigate AI service logs |
| P99 latency | > 5s over 5 min | Check resource limits |
| Service unhealthy | > 2 min | Auto-restart or escalate |
| Disk usage | > 85% | Expand volume or clean old backups |
