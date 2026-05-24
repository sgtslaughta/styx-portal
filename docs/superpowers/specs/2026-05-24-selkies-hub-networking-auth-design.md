# Selkies Hub — Networking & Auth Design Spec

**Date:** 2026-05-24
**Scope:** Networking layer + Auth integration (Sub-projects 3 & 4 of 4)
**Status:** Draft

## Overview

Configure Traefik reverse proxy, Cloudflare Tunnel routing, and Authentik ForwardAuth for the Selkies Hub platform. All config-only — no application code changes. Cloudflare handles TLS at the edge; Traefik operates HTTP-only behind the tunnel.

## Architecture

```
Client → Cloudflare Edge (TLS termination)
       → cloudflared tunnel (encrypted tunnel)
       → Traefik (:80 HTTP entrypoint)
       → ForwardAuth check → Authentik outpost (auth.domain.com)
       → Route to service based on Host header
```

## Components

### Cloudflare Tunnel

Single `cloudflared` container with tunnel token. Tunnel configured in Cloudflare dashboard:
- `domain.com` → `http://traefik:80`
- `*.domain.com` → `http://traefik:80`

The wildcard route is critical — it allows dynamically-created Selkies instances to be immediately accessible without CF dashboard changes.

### Traefik

HTTP-only reverse proxy. No local TLS — Cloudflare terminates it.

**Static config (`traefik.yml`):**
- Single entrypoint: `web` on port 80
- Docker provider: auto-discover containers via labels
- File provider: loads dynamic config for ForwardAuth middleware

**Dynamic config (`traefik/dynamic.yml`):**
- Defines `authentik` ForwardAuth middleware
- Points to Authentik outpost at `http://auth.domain.com/outpost.goauthentication.com/auth/traefik`

### Authentik ForwardAuth

External Authentik instance (already running). Traefik ForwardAuth middleware:
1. Every request → Traefik sends sub-request to Authentik outpost
2. Authentik returns 200 (authenticated) or 401 (redirect to login)
3. On 200, Authentik passes identity headers: `X-Authentik-Username`, `X-Authentik-Groups`, `X-Authentik-Email`
4. Backend can read these headers for user identification

**Auth bypass:** The Authentik outpost URL itself must NOT have ForwardAuth (circular dependency). Achieved via Traefik label override on the route.

## Routing Table

| Subdomain | Service | Port | Auth | Notes |
|-----------|---------|------|------|-------|
| `${DOMAIN}` | Frontend | 3000 | Yes | Main dashboard |
| `api.${DOMAIN}` | Backend | 8000 | Yes | API endpoints |
| `traefik.${DOMAIN}` | Traefik Dashboard | 8080 | Yes | Admin only |
| `auth.${DOMAIN}` | Authentik Outpost | external | **No** | Must be public for login flow |
| `*.${DOMAIN}` | Selkies instances | 3001 | Yes | Dynamic, label-based |

## File Changes

### traefik/traefik.yml (replace)

```yaml
api:
  dashboard: true
  insecure: true

entryPoints:
  web:
    address: ":80"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    network: selkies-hub
    watch: true
  file:
    filename: /etc/traefik/dynamic.yml
    watch: true
```

- Removed HTTPS entrypoint (CF handles TLS)
- Removed HTTP→HTTPS redirect (not needed)
- Added file provider for ForwardAuth middleware definition

### traefik/dynamic.yml (new)

```yaml
http:
  middlewares:
    authentik:
      forwardAuth:
        address: "http://${AUTHENTIK_HOST}/outpost.goauthentication.com/auth/traefik"
        trustForwardHeader: true
        authResponseHeaders:
          - X-Authentik-Username
          - X-Authentik-Groups
          - X-Authentik-Email
          - X-Authentik-Name
          - X-Authentik-Uid
```

Note: Traefik file provider doesn't support env var interpolation. The `AUTHENTIK_HOST` value will be written directly during setup. We provide a setup script that generates this file from `.env`.

### docker-compose.yml (update)

Changes:
- Traefik: remove ports 443, remove cert volume, mount dynamic.yml, use `web` entrypoint in labels
- All services: change entrypoint labels from `websecure` to `web`, add `authentik@file` middleware
- cloudflared: no changes (already correct)
- Backend: add screenshots volume

### .env.example (update)

Add:
```
AUTHENTIK_HOST=auth.yourdomain.com
```

### scripts/generate-config.sh (new)

Shell script that reads `.env` and generates `traefik/dynamic.yml` with the correct Authentik host. Run once during setup.

```bash
#!/bin/bash
source .env
envsubst < traefik/dynamic.yml.tmpl > traefik/dynamic.yml
```

### traefik/dynamic.yml.tmpl (new)

Template for dynamic config with `${AUTHENTIK_HOST}` placeholder.

## Docker Compose Service Labels

### Frontend
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.frontend.rule=Host(`${DOMAIN}`)
  - traefik.http.routers.frontend.entrypoints=web
  - traefik.http.routers.frontend.middlewares=authentik@file
  - traefik.http.services.frontend.loadbalancer.server.port=3000
```

### Backend
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.api.rule=Host(`api.${DOMAIN}`)
  - traefik.http.routers.api.entrypoints=web
  - traefik.http.routers.api.middlewares=authentik@file
  - traefik.http.services.api.loadbalancer.server.port=8000
```

### Traefik Dashboard
```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.dashboard.rule=Host(`traefik.${DOMAIN}`)
  - traefik.http.routers.dashboard.entrypoints=web
  - traefik.http.routers.dashboard.middlewares=authentik@file
  - traefik.http.routers.dashboard.service=api@internal
```

### Dynamic Selkies Instances (generated by backend)

The backend's `traefik_labels.py` already generates these. Update to use `web` entrypoint and add auth middleware:
```yaml
traefik.enable: "true"
traefik.http.routers.{id}.rule: "Host(`{subdomain}.{domain}`)"
traefik.http.routers.{id}.entrypoints: "web"
traefik.http.routers.{id}.middlewares: "authentik@file"
traefik.http.services.{id}.loadbalancer.server.port: "3001"
selkies-hub.managed: "true"
selkies-hub.instance-id: "{id}"
selkies-hub.template: "{template_name}"
```

## Backend Changes

### traefik_labels.py

Update `generate_traefik_labels()`:
- Change entrypoint from `websecure` to `web`
- Always include `authentik@file` middleware (replace optional `auth_middleware` param)

### config.py

Add `AUTHENTIK_MIDDLEWARE: str = "authentik@file"` setting.

## Design Decisions

1. **No local TLS** — Cloudflare tunnel encrypts client↔edge and edge↔origin. Internal Docker network is trusted. Adding local TLS is complexity without security gain.
2. **File provider for ForwardAuth** — Docker labels can't define middleware used by other containers. File provider makes the middleware globally available as `authentik@file`.
3. **Template + generate script** — Traefik file provider doesn't interpolate env vars. Simple script reads `.env` and writes the config.
4. **Global auth by default** — Every route gets ForwardAuth. Safer default; auth bypass is explicit per-route.
5. **Wildcard CF tunnel route** — New Selkies instances get subdomains automatically without CF dashboard changes.
