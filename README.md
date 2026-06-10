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
| Docker | docker-py via read-only socket-proxy |
| Proxy | Traefik v3 (label-based auto-discovery) |
| Tunnel / TLS | Cloudflare Tunnel or Let's Encrypt (direct mode) |
| Auth | Native JWT + OIDC/OAuth SSO |
| Frontend | React |

## Upgrading from Selkies Hub (rebrand)

The rebrand renames the Docker network and SQLite DB. On an existing install:

```bash
docker compose down
docker network rm selkies-hub        # old network
rm -f backend/data/selkies-hub.db    # old DB (state is recreated on first run)
docker compose up -d                 # recreates the styx-portal network + fresh DB
```

## Quick Start

See [docs/QUICKSTART.md](docs/QUICKSTART.md) for a 5-minute setup guide with Cloudflare Tunnel.

In brief: `cp .env.example .env`, set `DOMAIN` and `CF_TUNNEL_TOKEN`, then `docker compose up -d`.

## Documentation

- [Quick Start](docs/QUICKSTART.md) — get running in 5 minutes
- [Production Deployment](docs/PRODUCTION.md) — TLS, backups, hardening, monitoring
- [GPU Setup](docs/GPU.md) — drivers, runtime, troubleshooting
- [Admin Guide](docs/ADMIN.md) — users, SSO, templates, audit, quotas

## Deployment Modes

Two deployment modes are supported:

- **tunnel (default)** — Cloudflare Tunnel edge for TLS; backend traffic is plaintext. Set `COMPOSE_PROFILES=tunnel` and `DEPLOY_MODE=tunnel`.
- **direct** — Traefik owns ports 80/443 with Let's Encrypt wildcard TLS. Set `COMPOSE_PROFILES=direct` and `DEPLOY_MODE=direct`. See [docs/PRODUCTION.md](docs/PRODUCTION.md) for setup.

## Secrets Management

- **JWT_SECRET:** Leave empty in `.env` for automatic generation on first start. The generated secret is saved to the persistent data volume at `/app/data/secrets.json` (mode 0600). **Back this file up** — losing it logs out all users and invalidates OAuth provider secrets. See [docs/PRODUCTION.md](docs/PRODUCTION.md) for backup procedures.

## Security

All deployments are hardened by default:

- Instances confined (no privileged mode; `cap_drop: ALL` + minimal needed caps)
- Docker socket proxy (read-only, dangerous ops denied)
- Per-user instance networks (container isolation)
- Refresh-token reuse detection (RFC 9700)
- Audit log (auth, roles, instances, providers)
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- DinD admin-only + memory/CPU limits required

See [docs/PRODUCTION.md](docs/PRODUCTION.md) for full details.

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

## Authentication

**Native JWT + OIDC/OAuth SSO** — admin-invite-only user creation, single-use invite links, Argon2id password hashing, CSRF protection, rate limiting, per-user instance ownership.

For SSO setup, see [docs/ADMIN.md](docs/ADMIN.md).

## Project Status

- [x] Backend orchestration + Docker socket proxy
- [x] Frontend dashboard
- [x] Native JWT auth + SSO (OIDC/OAuth)
- [x] Traefik auto-discovery + TLS (Cloudflare Tunnel / Let's Encrypt)
- [x] Security hardening (confined containers, audit log, per-user networks)
- [x] Diagnostics + Health monitoring

## License

Private project.
