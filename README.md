# Styx Portal

Self-hosted remote desktop platform managing Selkies-based containers. Replaces Kasm Workspaces with better performance via WebRTC streaming.

## Architecture

```
Cloudflare Tunnel → Traefik (auto-discovery) → Services
                                                ├── React Frontend (:3000)
                                                ├── FastAPI Backend (:8000)
                                                └── N × Selkies Containers (:3001)
```

- **Backend** manages sibling containers via docker-socket-proxy (read-only, filtered)
- **Traefik** auto-discovers containers via Docker labels
- **Cloudflare Tunnel** routes `*.domain.com` to Traefik (tunnel mode)
- **TLS** via Cloudflare Tunnel edge (tunnel) or Let's Encrypt DNS-01 wildcard (direct)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+, FastAPI, SQLModel, aiosqlite |
| Docker | docker-py via socket-proxy |
| Proxy | Traefik v3 (label-based auto-discovery) |
| Tunnel | Cloudflare Tunnel |
| Auth | Native JWT + OIDC/OAuth SSO |
| Frontend | React (planned) |

## Upgrading from Selkies Hub (rebrand)

The rebrand renames the Docker network and SQLite DB. On an existing install:

```bash
docker compose down
docker network rm selkies-hub        # old network
rm -f backend/data/selkies-hub.db    # old DB (state is recreated on first run)
docker compose up -d                 # recreates the styx-portal network + fresh DB
```

## Quick Start

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Edit .env with your domain and Cloudflare Tunnel token
#    DOMAIN=your.domain.com
#    CF_TUNNEL_TOKEN=<your-token>
#    Leave JWT_SECRET empty; a strong secret will be auto-generated on first start.

# 3. Start infrastructure
docker compose up -d

# 4. Access the backend health check
curl http://localhost:8000/api/health
```

## Deployment Modes

Set `COMPOSE_PROFILES` and `DEPLOY_MODE` to the same value to select your ingress strategy:

### tunnel (default)
- **TLS:** Cloudflare Tunnel terminates TLS at the edge; backend traffic is plaintext.
- **Setup:** Set `DOMAIN` and `CF_TUNNEL_TOKEN` in `.env`; no port exposure on the host.
- **Best for:** Public deployments with Cloudflare, zero-trust networking.

### direct
- **TLS:** Traefik owns ports 80/443; automatic Let's Encrypt wildcard certificates via DNS-01.
- **Setup:** Set `DOMAIN`, `LE_EMAIL`, and `CF_DNS_API_TOKEN` (or equivalent for your DNS provider) in `.env`. See `traefik/traefik-direct.yml` for provider-specific ACME configuration.
- **Best for:** Self-hosted on a static IP, direct domain control.

## Secrets Management

- **JWT_SECRET:** Leave empty in `.env` for automatic generation. On first start, a strong secret is generated and saved to `/app/data/secrets.json` (mode 0600) on the persistent data volume. **Back this file up** — losing it will log out all users and invalidate stored OAuth client secrets.
- **To pin your own secret:** `openssl rand -base64 48` and set `JWT_SECRET` in `.env` before first start.
- **OAuth client secrets:** Encrypted at rest using a Fernet key derived from `JWT_SECRET`.

## Instance Quotas

Set `MAX_INSTANCES_PER_USER` to limit concurrent instances per non-admin user (default: 3). Set to 0 for unlimited. Admins are always exempt.

## Security Notes

- **Confined containers:** Instances run confined by default (no privileged mode or host access).
- **DinD templates:** Templates with Docker-in-Docker are privileged and admin-only; they **require** memory and CPU resource limits in their spec.
- **Traefik dashboard:** Disabled by default for security.
- **Audit log:** Admin users can fetch the audit log at `GET /api/audit` (JSON format).
- **Socket proxy:** Backend talks to a read-only docker-socket-proxy sidecar, not the raw Docker socket.

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
