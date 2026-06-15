# Quick Start

Get Styx Portal running in 5 minutes using Cloudflare Tunnel (the default).

## Prerequisites

- Docker + Docker Compose v2
- A domain name (e.g., `portal.example.com`)
- [Cloudflare Tunnel token](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (free tier OK)

## Steps

1. **Clone and configure:**
   ```bash
   git clone <repo>
   cd styx-portal
   cp .env.example .env
   ```

2. **Set required environment variables:**
   ```bash
   # Edit .env:
   DOMAIN=your.domain.com
   CF_TUNNEL_TOKEN=<your-cloudflare-token>
   ```
   Leave `JWT_SECRET` empty — a strong secret is auto-generated on first boot and saved to the persistent data volume.

3. **Start services:**
   ```bash
   docker compose up -d
   ```

   (`COMPOSE_PROFILES=tunnel` is the default, so Cloudflare Tunnel mode starts automatically.)

   The `backend` and `frontend` images are published to GHCR on each release, so
   no local build is needed. To pin a release instead of `latest`, set `STYX_TAG`
   in `.env` (e.g. `STYX_TAG=1.0.0`). To build from source instead, run
   `docker compose up -d --build`. If the GHCR packages are private, run
   `docker login ghcr.io` first (see `.env.example`).

   **Using workstations:** if you plan to enroll physical workstations, expose
   Traefik's ports on your LAN by uncommenting them in `docker-compose.yml`:

   ```yaml
   traefik:
     profiles: ["tunnel"]
     image: traefik:v3.4
     container_name: styx-traefik
     restart: unless-stopped
     # Workstation streaming: uncomment to expose the portal on your LAN so
     # physical workstations can enroll and stream. The backend auto-generates
     # a self-signed cert for the LAN address (served on :443) and pins it in
     # the enrollment command — no manual TLS setup needed.
     ports:
       - "80:80"
       - "443:443"
   ```

4. **Complete setup:**
   - Open `https://your.domain.com` in your browser
   - You'll be redirected to `/setup` — create an admin account
   - The setup page includes an **Environment Check** panel showing Docker, database, and network status; green lights mean you're ready

5. **Done!**
   - Log in with your admin credentials
   - Invite additional users via **System → Users** (generates a single-use link)
   - Launch instances from templates

## Important: Back Up Your Secrets

The auto-generated `JWT_SECRET` is stored in the `db-data` Docker volume at `/app/data/secrets.json` (mode 0600). **Losing this file logs everyone out and invalidates stored OAuth provider secrets.**

Back it up regularly:
```bash
docker cp styx-backend:/app/data/secrets.json ./secrets.json.backup
```

## What's Next?

- To enable GPU: see [docs/GPU.md](GPU.md)
- For production TLS (Let's Encrypt wildcard certs): see [docs/PRODUCTION.md](PRODUCTION.md)
- For user/SSO/template management: see [docs/ADMIN.md](ADMIN.md)
