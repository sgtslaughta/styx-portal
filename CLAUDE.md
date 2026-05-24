# Selkies Hub — Development Guide

## Project Structure

```
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
    services/
      docker_manager.py    Docker API wrapper
      traefik_labels.py    Label generation for Traefik routing
      session_monitor.py   Idle detection background loop
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

## Testing

- Tests use in-memory SQLite and mocked Docker client
- `conftest.py` overrides FastAPI dependency injection for DB sessions
- Docker manager tests mock `docker.DockerClient.from_env()`
- Instance tests mock `get_docker_manager` dependency

## Environment

- Python 3.12+ required
- Venv at `backend/.venv`
- Dependencies in `backend/pyproject.toml`
