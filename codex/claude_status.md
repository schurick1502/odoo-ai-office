# Statusbericht: Odoo AI Office / Steuerbüro-Framework

**Erstellt von:** Cloudcode (Worker) – Claude Opus 4.6
**Datum:** 2026-02-15
**Repository:** https://github.com/schurick1502/odoo-ai-office
**PR #1:** https://github.com/schurick1502/odoo-ai-office/pull/1 (dev -> main)

---

## 1. Projektziel

Das Projekt **Odoo AI Office** ist ein KI-gestütztes Steuerbüro-Framework für Odoo 18. Es automatisiert Buchhaltungs-Workflows mit einem **Human-in-the-Loop**-Ansatz: KI-Agenten analysieren Belege, schlagen Buchungen vor, aber nur autorisierte Personen (Approver) dürfen final buchen.

### Kernprinzipien
- **GoBD/Audit-fähig**: Jede Agent-Aktion wird in einem unveränderlichen Audit-Log protokolliert
- **No-Auto-Posting**: KI darf niemals automatisch buchen – nur Human Approver
- **Docker-first**: Alles läuft containerisiert (Dev + Prod)
- **Upgrade-fähig**: SemVer, Changelog, migrationsfreundlich

### Architektur
```
┌─────────────────┐     REST/JSON      ┌──────────────────────┐
│  Odoo 18        │ ◄────────────────► │  AI Office Service   │
│  (Addon)        │                    │  (FastAPI)           │
│                 │                    │                      │
│  account.ai.*   │                    │  /v1/orchestrate     │
└────────┬────────┘                    └──────────┬───────────┘
         │                                        │
         ▼                                        ▼
    PostgreSQL                           LLM Providers (Zukunft)
```

### State Machine
```
new → enriched → proposed → approved → posted → exported
                                 ↘ needs_attention
                                 ↘ failed
```

---

## 2. Abgeschlossene Phasen (M0 – M2.5)

### Phase M0: Repository & Infrastruktur

**Was wurde getan:**
- GitHub Repository `odoo-ai-office` angelegt (public, MIT-Lizenz)
- Branch-Strategie: `main` (stable) + `dev` (Entwicklung)
- Komplette Verzeichnisstruktur nach Plan aufgebaut
- Docker Compose für Dev und Prod konfiguriert
- CI/CD Pipelines (GitHub Actions) eingerichtet
- 10 Milestones, 22 Labels und 51 Issues auf GitHub erstellt

### Phase M1: Odoo Addon Foundation

**Was wurde getan:**
- Odoo 18 Addon `account_ai_office` vollständig implementiert
- 4 Datenmodelle mit Geschäftslogik
- Security-System mit 3 Gruppen und Record Rules
- Vollständiges UI mit Menü, Views und Filtern
- Tests für State Machine und Zugriffsrechte
- Seed-Daten für Default-Policies

### Phase M2: FastAPI Service

**Was wurde getan:**
- FastAPI Microservice mit Health-Endpoint und Orchestrierungs-API
- Pydantic v2 Schemas für Request/Response-Verträge
- DummyAgent als MVP-Platzhalter für echte KI-Agenten
- Contract Tests zur Schema-Validierung
- Docker-Image-Definition

### Phase M2.5: Odoo ↔ Service Integration

**Was wurde getan:**
- `action_run_orchestrator()` Methode im Case-Modell
- "Run AI" Button in der Case-Form (sichtbar bei state new/enriched)
- HTTP-Kommunikation mit dem Service
- Suggestions werden zurückgeschrieben + Audit Log
- Konfigurierbare Service-URL via `ir.config_parameter`

---

## 3. Erstellte Dateien (34 Dateien)

### 3.1 Projekt-Root (5 Dateien)

| Datei | Beschreibung |
|-------|-------------|
| `.gitignore` | Python, Docker, IDE, OS-spezifische Ignores |
| `.env.example` | Template für Umgebungsvariablen (DB, Odoo, Service) |
| `README.md` | Projektdokumentation mit Quick Start, Architektur, Dev Workflow |
| `compose.dev.yml` | Docker Compose für Entwicklung (3 Services, lokale Mounts, Healthchecks) |
| `compose.prod.yml` | Docker Compose für Produktion (GHCR Images, Restart-Policies) |

### 3.2 Odoo Addon – `odoo/addons/account_ai_office/` (19 Dateien)

#### Core Module
| Datei | Beschreibung |
|-------|-------------|
| `__init__.py` | Root-Init, importiert `models` |
| `__manifest__.py` | Modul-Manifest: Name, Version 18.0.1.0.0, Abhängigkeiten (base, account, mail), application=True |

#### Modelle (`models/`)
| Datei | Beschreibung |
|-------|-------------|
| `models/__init__.py` | Importiert alle 4 Modell-Module |
| `models/ai_case.py` | **Kernmodell** `account.ai.case` – State Machine mit 8 States, Action-Methoden (propose/approve/post/export/reset/needs_attention), Audit-Logging, `action_run_orchestrator()` für Service-Integration. Erbt `mail.thread` + `mail.activity.mixin`. |
| `models/ai_suggestion.py` | `account.ai.suggestion` – KI-Vorschläge mit Typ, JSON-Payload, Konfidenz, Risiko-Score, Markdown-Erklärung, Agent-Name. Verknüpft via `case_id` (cascade delete). |
| `models/ai_audit_log.py` | `account.ai.audit_log` – Unveränderliches Audit-Log. Speichert Actor (User/Agent), Aktion, Before/After-JSON. `unlink()` überschrieben: nur Superuser darf löschen (GoBD-Compliance). |
| `models/ai_policy.py` | `account.ai.policy` – Konfigurierbare Regeln pro Company/Supplier/Category. JSON-Regeln, Versionierung, zeitliche Aktivierung. |

#### Security (`security/`)
| Datei | Beschreibung |
|-------|-------------|
| `security/security.xml` | Modul-Kategorie "AI Office", 3 hierarchische Gruppen: `ai_office_user` → `ai_office_approver` → `ai_office_admin`. Company-basierte Record Rules für alle 4 Modelle (Multi-Company-Isolation). |
| `security/ir.model.access.csv` | 12 Zugriffsregeln (4 Modelle x 3 Gruppen). User: read/write/create auf Cases+Suggestions, read-only auf Audit+Policies. Admin: voller CRUD. |

#### Views (`views/`)
| Datei | Beschreibung |
|-------|-------------|
| `views/menu.xml` | Root-Menü "AI Office" mit Untermenüs: Inbox, Cases, Suggestions, Audit Logs, Policies, Settings (admin-only). |
| `views/ai_case_views.xml` | Tree (mit Badge-States), Form (Header-Buttons: Run AI/Propose/Approve/Post/Export/Reset/Needs Attention, StatusBar, Notebook mit Documents/Suggestions/Audit Trail), Search (State-Filter, Group-By). 2 Actions: alle Cases + Inbox (gefiltert). |
| `views/ai_suggestion_views.xml` | Tree + Form Views mit Progressbar-Widgets für Konfidenz und Risiko. |
| `views/ai_audit_log_views.xml` | Read-only Tree + Form Views (create/delete/edit deaktiviert). |
| `views/ai_policy_views.xml` | Tree + Form Views für Policy-Verwaltung. |

#### Daten (`data/`)
| Datei | Beschreibung |
|-------|-------------|
| `data/seed_policies.xml` | Default-Policy "Default Threshold Policy" mit confidence_threshold=0.8, risk_score_max=0.3. noupdate=1. |

#### Tests (`tests/`)
| Datei | Beschreibung |
|-------|-------------|
| `tests/__init__.py` | Importiert beide Test-Module. |
| `tests/test_state_machine.py` | 8 TransactionCase Tests: Case-Erstellung (state=new), vollständiger Transition-Pfad, ungültiges Approve von new, needs_attention von jedem State, Audit-Log nach propose, Reset nur von needs_attention/failed, Export nur von posted, Suggestion-Count. |
| `tests/test_acl.py` | 6 TransactionCase Tests: User kann nicht approven, User kann nicht posten, Approver kann approven, Approver kann posten, Audit-Log nicht löschbar (non-superuser). |

#### Statische Assets
| Datei | Beschreibung |
|-------|-------------|
| `static/description/icon.png` | 128x128 blaues (#2a62af) PNG-Icon für App-Menü. |

### 3.3 FastAPI Service – `service/` (15 Dateien)

#### Konfiguration
| Datei | Beschreibung |
|-------|-------------|
| `pyproject.toml` | Projekt-Metadaten, Dependencies: FastAPI, uvicorn, pydantic, httpx. Dev-Dependencies: pytest, pytest-asyncio. |
| `Dockerfile` | Python 3.12-slim, installiert aus pyproject.toml, exponiert Port 8100, startet uvicorn. |

#### Applikation (`app/`)
| Datei | Beschreibung |
|-------|-------------|
| `app/__init__.py` | Leere Init-Datei. |
| `app/main.py` | FastAPI App "AI Office Service" v0.1.0. Inkludiert Orchestrator-Router. `GET /health` → `{"status": "ok", "version": "0.1.0"}`. |

#### Schemas (`app/schemas/`)
| Datei | Beschreibung |
|-------|-------------|
| `app/schemas/__init__.py` | Leere Init-Datei. |
| `app/schemas/base.py` | Pydantic v2 `HealthResponse` Model (status, version). |
| `app/schemas/orchestrate.py` | `OrchestrateRequest` (case_id, request_id, context), `Suggestion` (7 Felder), `OrchestrateResponse` (case_id, request_id, suggestions[], status). |

#### Orchestrator (`app/orchestrator/`)
| Datei | Beschreibung |
|-------|-------------|
| `app/orchestrator/__init__.py` | Leere Init-Datei. |
| `app/orchestrator/router.py` | APIRouter mit Prefix `/v1`. `POST /orchestrate` ruft DummyAgent auf und gibt OrchestrateResponse zurück. |

#### Agents (`app/agents/`)
| Datei | Beschreibung |
|-------|-------------|
| `app/agents/__init__.py` | Leere Init-Datei. |
| `app/agents/dummy_agent.py` | `DummyAgent` Klasse mit async `run()`. Gibt 1 Dummy-Buchungsvorschlag zurück: Soll 4400, Haben 1200, Betrag 119.00, Konfidenz 0.85, Risiko 0.1. |

#### Tools (Platzhalter)
| Datei | Beschreibung |
|-------|-------------|
| `app/tools/__init__.py` | Leere Init-Datei (für zukünftige Tool-Integrationen). |

#### Tests (`tests/`)
| Datei | Beschreibung |
|-------|-------------|
| `tests/__init__.py` | Leere Init-Datei. |
| `tests/test_health.py` | Testet `GET /health`: Status 200, JSON mit status="ok" und version. |
| `tests/test_orchestrate_contract.py` | 3 Tests: Suggestions werden zurückgegeben mit korrekter Struktur, leerer Input ergibt 422, Schema-Vollständigkeit (payload ist dict, explanation ist str). |

### 3.4 CI/CD – `.github/workflows/` (2 Dateien)

| Datei | Beschreibung |
|-------|-------------|
| `.github/workflows/ci.yml` | Trigger: PR + Push auf main/dev. Jobs: (1) ruff lint für Service + Addon, (2) pytest für Service, (3) Docker Build des Service-Images. |
| `.github/workflows/release.yml` | Trigger: Tag `v*`. Login bei GHCR, Build + Push mit Version-Tag + latest, GitHub Release mit auto-generierten Notes. |

---

## 4. Git-Historie (6 Commits auf `dev`)

| Commit | Typ | Beschreibung |
|--------|-----|-------------|
| `e7c4730` | chore | Initial repo setup mit .gitignore, .env.example, LICENSE, README |
| `3cb4faa` | feat | Docker Compose dev/prod mit db, odoo, ai_office_service |
| `47a9ede` | feat | Odoo Addon account_ai_office mit Models, Views, Security, Tests |
| `f516c6e` | feat | FastAPI ai_office_service mit /health, /v1/orchestrate, DummyAgent |
| `02f3bbc` | chore | CI/CD Workflows für lint, test, build, release |
| `75e2c05` | feat | Odoo ↔ Service Integration mit "Run AI" Button |

---

## 5. GitHub Project Management

### Milestones (10)

| Milestone | Issues | Beschreibung |
|-----------|--------|-------------|
| M0: Repo & CI | 7 | Repository, Docker, CI/CD |
| M1: Odoo Foundation | 11 | Addon-Grundlage: Modelle, Views, Security |
| M2: Service & Orchestrator | 7 | FastAPI Service-Skeleton |
| M2.5: Odoo Integration | 5 | Odoo ↔ Service Kommunikation |
| M3: Intake Pipeline | 4 | Dokumenten-Eingang, OCR, E-Mail-Parsing |
| M4: Kontierung | 4 | KI-gestützte Kontozuordnung |
| M5: Compliance | 3 | GoBD-Konformität, Validierung |
| M6: OPOS | 3 | Offene-Posten-Abstimmung |
| M7: Export Paket | 3 | DATEV-Export, Steuerberater-Reporting |
| M8: Pilot/Hardening | 4 | Produktion, Monitoring, Load Tests |

### Labels (22 custom)

- **Phase:** phase:M0 bis phase:M8 (10 Labels)
- **Typ:** type:feat, type:fix, type:test, type:docs, type:chore (5 Labels)
- **Priorität:** prio:P0 (Critical), prio:P1 (High), prio:P2 (Medium) (3 Labels)
- **Bereich:** area:odoo, area:service, area:infra, area:ci (4 Labels)

### Issues (51 total, #2 bis #52)

Granular verteilt auf alle Milestones mit passenden Labels für Phase, Typ, Priorität und Bereich.

---

## 6. Nächste Schritte

### Sofort (Smoke Test)
1. PR #1 mergen (dev → main)
2. `docker compose -f compose.dev.yml up -d`
3. Addon in Odoo installieren
4. Case erstellen → "Run AI" klicken → Suggestions prüfen

### Phase M3: Intake Pipeline (nächste Entwicklungsphase)
- E-Mail-Anhang-Intake
- OCR/Dokumenten-Parsing Agent
- Automatische Case-Erstellung aus Belegen

### Phase M4: Kontierung
- LLM-basierte Kontozuordnung (SKR03/04)
- Lieferanten-spezifische Policy-Anwendung
- `account.move` Erstellung aus genehmigten Vorschlägen

---

## 7. Technische Details

### Docker Services (Dev)

| Service | Image | Port | Healthcheck |
|---------|-------|------|-------------|
| `db` | postgres:16.4-alpine | 5433 | pg_isready |
| `odoo` | odoo:18.0 | 8069 | curl /web/health |
| `ai_office_service` | build ./service | 8100 | curl /health |

### Security-Gruppen

| Gruppe | Berechtigungen |
|--------|---------------|
| `ai_office_user` | Cases/Suggestions lesen/erstellen, Audit Logs lesen |
| `ai_office_approver` | + Cases freigeben (approve) und buchen (post) |
| `ai_office_admin` | + Policies verwalten, voller CRUD auf alles |

### API-Endpunkte (Service)

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/health` | Health Check → `{"status": "ok", "version": "0.1.0"}` |
| POST | `/v1/orchestrate` | KI-Orchestrierung → Suggestions |

### Odoo → Service Kommunikation

```python
# In account.ai.case.action_run_orchestrator():
requests.post(
    f"{service_url}/v1/orchestrate",
    json={
        "case_id": self.id,
        "request_id": str(uuid.uuid4()),
        "context": {
            "partner_id": self.partner_id.id,
            "partner_name": self.partner_id.name,
            "period": self.period,
            "company_id": self.company_id.id,
        },
    },
    timeout=30,
)
```

---

*Dieser Bericht wurde automatisch von Cloudcode (Worker) erstellt.*
