# Deployment Guide

## Prerequisites

- Docker Engine 24+ and Docker Compose v2.20+
- Linux host with at least 4 GB RAM and 2 CPU cores
- DNS / reverse proxy configured (nginx, Traefik, or Caddy)
- TLS certificate (Let's Encrypt recommended)

## 1. Clone and Configure

```bash
git clone https://github.com/schurick1502/odoo-ai-office.git
cd odoo-ai-office
cp .env.example .env
```

Edit `.env` and set ALL required values. See [Environment Variable Reference](./env-reference.md).

**Critical:** Never deploy with empty or default passwords. Generate secure passwords:

```bash
openssl rand -base64 24
```

## 2. Start Services

```bash
docker compose -f compose.prod.yml up -d
```

Verify all services are healthy:

```bash
docker compose -f compose.prod.yml ps
```

Expected: all 3 services showing `healthy` status.

## 3. Initialize Odoo

On first deployment:

1. Open `http://<host>:8069/web/database/manager`
2. Create database with the name matching `POSTGRES_DB` in `.env`
3. Install the `account_ai_office` module from Apps
4. Configure AI Office Service URL:
   - Settings > Technical > Parameters > System Parameters
   - Key: `ai_office.service_url`
   - Value: `http://ai_office_service:8100`

## 4. Verify Integration

```bash
# AI Service health
curl http://localhost:8100/health

# Prometheus metrics
curl http://localhost:8100/metrics

# Odoo web health
curl http://localhost:8069/web/health
```

Then in the Odoo UI:
1. Navigate to AI Office > Inbox
2. Create a test case
3. Click "Run AI" — should generate suggestions

## 5. Reverse Proxy (nginx example)

```nginx
server {
    listen 443 ssl;
    server_name office.example.com;

    ssl_certificate /etc/letsencrypt/live/office.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/office.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8069;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The AI service port (8100) should **not** be exposed externally — it is only accessed by the Odoo container via the Docker internal network.

## 6. Backups

### Database

```bash
docker compose -f compose.prod.yml exec db \
  pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Filestore

```bash
docker run --rm -v odoo-ai-office_odoo-filestore:/data -v $(pwd):/backup \
  alpine tar czf /backup/filestore_$(date +%Y%m%d).tar.gz -C /data .
```

Schedule both as daily cron jobs.

## 7. Updates

### Service update (new image version)

```bash
export SERVICE_VERSION=0.3.0
docker compose -f compose.prod.yml pull ai_office_service
docker compose -f compose.prod.yml up -d ai_office_service
```

### Odoo addon update

```bash
docker compose -f compose.prod.yml restart odoo
# Then in Odoo: Apps > Update Apps List > Upgrade account_ai_office
```
