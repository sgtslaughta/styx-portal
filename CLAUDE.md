# Styx Portal — Development Guide

## Project Structure

```
agent/             Workstation enrollment and agent daemon
  enroll.sh        Enrollment script (preflight E01–E08, install, register)
  styx_agent.py    Agent daemon (selkies supervision, heartbeat, doctor, uninstall)
  uninstall.sh     Standalone removal script
  tests/           Agent unit tests
backend/           FastAPI application
  app/
    config.py      Pydantic settings (env-driven)
    database.py    SQLite engine, session factory, template seeding
    models.py      SQLModel table models
    schemas.py     Pydantic request/response schemas
    main.py        FastAPI app, lifespan, router registration
    routers/
      templates.py Template CRUD
      instances.py Instance lifecycle + Docker integration
      workstations.py   Workstation admin CRUD + token minting
      enroll.py    Public enrollment API (register, script/artifact serving)
      agent.py     Agent-facing API (heartbeat, deregister)
    services/
      docker_manager.py    Docker API wrapper
      traefik_labels.py    Label generation for Traefik routing
      session_monitor.py   Idle detection background loop
      workstations.py      Subdomain slug, stale-offline detection
      artifacts.py         Selkies tarball cache + download
      route_writer.py      Traefik dynamic config (extended for workstation routes)
  tests/           pytest test suite
docker-compose.yml Infrastructure services
traefik/           Traefik static config
templates/         Default JSON templates (seeded on first run)
plans/             Original requirements and implementation plans
```

## Commands

```bash
# Run tests
cd backend && .venv/bin/python -m pytest -v

# Run tests with coverage
cd backend && .venv/bin/python -m pytest --tb=short

# Lint
cd backend && .venv/bin/python -m ruff check app/ tests/

# Run server (dev)
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

# Docker compose
docker compose up -d
```

## Key Design Decisions

1. Docker socket mount (not DinD) — containers are host peers
2. SQLite — single host, single user, zero config
3. Named Docker volumes — portable, Docker-managed
4. Traefik auto-discovery via labels — no config reloads
5. Subdomain routing — cleaner for WebRTC/WebSocket
6. SQLModel — one class = DB model + API schema
7. **Auth (Phase 1):** Native JWT auth with per-user instance ownership, Argon2id hashing, CSRF (double-submit), rate limiting, and security headers (CSP/HSTS/X-Frame-Options) enforced.
8. **SSO (Phase 2):** Federated identities via OIDC/OAuth2 (authlib). Providers stored in `oauth_providers` with Fernet-encrypted secrets (key=HKDF(JWT_SECRET)). Identities in `federated_identities` table (unique provider+subject). Pre-authorized-only provisioning: verified email must match existing user or open invite. Identity details fetched from OIDC userinfo endpoint (no JWKS/id_token parsing).

## Testing

- Tests use in-memory SQLite and mocked Docker client
- `conftest.py` overrides FastAPI dependency injection for DB sessions
- Docker manager tests mock `docker.DockerClient.from_env()`
- Instance tests mock `get_docker_manager` dependency

## Environment

- Python 3.12+ required
- Venv at `backend/.venv`
- Dependencies in `backend/pyproject.toml`
