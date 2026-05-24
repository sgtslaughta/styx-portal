# Selkies Hub

Self-hosted remote desktop platform managing Selkies-based containers. Replaces Kasm Workspaces with better performance via WebRTC streaming.

## Architecture

```
Cloudflare Tunnel → Traefik (auto-discovery) → Services
                                                ├── React Frontend (:3000)
                                                ├── FastAPI Backend (:8000)
                                                └── N × Selkies Containers (:3001)
```

- **Backend** manages sibling containers via Docker socket mount
- **Traefik** auto-discovers containers via Docker labels
- **Cloudflare Tunnel** routes `*.domain.com` to Traefik
- **Authentik** provides SSO via ForwardAuth middleware

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, SQLModel, aiosqlite |
| Docker | docker-py (socket mount) |
| Proxy | Traefik v3 (label-based auto-discovery) |
| Tunnel | Cloudflare Tunnel |
| Auth | Authentik (ForwardAuth) |
| Frontend | React (planned) |

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env
# Edit .env with your domain and CF tunnel token

# 2. Start infrastructure
docker compose up -d

# 3. Access API
curl http://localhost:8000/api/health
```

## Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
python -m pytest -v

# Run server locally
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

### Templates
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/templates` | List available templates |
| POST | `/api/templates` | Create template |
| GET | `/api/templates/{id}` | Get template details |
| PUT | `/api/templates/{id}` | Update template |
| DELETE | `/api/templates/{id}` | Delete template |

### Instances
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/instances` | List all instances |
| POST | `/api/instances` | Launch from template |
| POST | `/api/instances/{id}/start` | Start stopped instance |
| POST | `/api/instances/{id}/stop` | Stop (preserve volume) |
| DELETE | `/api/instances/{id}` | Destroy + optional volume cleanup |
| GET | `/api/instances/{id}/status` | Container status + health |
| POST | `/api/instances/{id}/keepalive` | Reset idle timer |
| PATCH | `/api/instances/{id}/session` | Override timeout settings |

## Default Templates

- **dev-desktop** — Linux desktop for development (no GPU)
- **workstation** — Full host access with GPU passthrough
- **gaming** — GPU-accelerated desktop for gaming

## Session Management

Background monitor polls every 60s. Per-template configurable:
- `idle_timeout` — time before warning (default 30m)
- `grace_period` — warning → auto-stop (default 5m)
- `timeout_action` — `stop` or `destroy`
- `never_timeout` — always-on override

## Project Status

- [x] Backend orchestration service
- [ ] Frontend React hub
- [ ] Networking layer (Traefik + Cloudflare setup)
- [ ] Auth integration (Authentik SSO)

## License

Private project.
