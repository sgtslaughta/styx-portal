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

## Authentication (Phase 1)

Native username/password auth with JWT in httpOnly cookies.

- **First run:** visit the app; you'll be redirected to `/setup` to create the admin account (one-time).
- **Users:** admin-invite-only. Admins generate single-use invite links from the **System → Users** panel.
- **Config:** set a strong `JWT_SECRET` (≥32 bytes) and `COOKIE_SECURE=true` in `.env` before exposing publicly.

Security: per-user instance ownership (admins see all), Argon2id password hashing, double-submit CSRF, rate limiting on auth endpoints, and security headers (CSP/HSTS/X-Frame-Options) are enforced.

## SSO / OAuth (Phase 2)

Federated identity via OIDC and OAuth2 providers (generic OIDC issuer discovery, Google, GitHub).

- **Provider setup:** Admins add providers in **System → OAuth providers** with issuer URL, client ID, and client secret; enable to activate.
- **Sign-in:** Users see "Sign in with <provider>" buttons on the login page; login succeeds only if the verified email matches an existing user or open invite (pre-authorized-only).
- **Account linking:** Logged-in users link/unlink providers under **System → Connected accounts** (cannot unlink the only login method).
- **Redirect URIs:** Register these with each provider:
  - Login: `https://<domain>/api/auth/oauth/<name>/callback`
  - Linking: `https://<domain>/api/auth/link/<name>/callback`
- **Secrets:** Client secrets are encrypted at rest using a Fernet key derived from `JWT_SECRET`; rotating `JWT_SECRET` requires re-entering provider secrets.

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
