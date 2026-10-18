# Production Deployment

Hardened checklist for production deployments, including TLS setup, backups, security posture, and monitoring.

## TLS Setup

### Cloudflare Tunnel (default, recommended for simplicity)

Already configured in `.env.example`. Set:
```bash
COMPOSE_PROFILES=tunnel
DEPLOY_MODE=tunnel
DOMAIN=your.domain.com
CF_TUNNEL_TOKEN=<your-token>
```

TLS terminates at Cloudflare's edge; backend traffic is plaintext but encrypted in transit. Traefik dashboard is disabled by default.

**Tunnel origin:** the tunnel's public hostname must point at `http://styx-traefik:80`. cloudflared sits alone with Traefik on the dedicated `styx-tunnel` network (172.31.254.0/28) and cannot reach `frontend` or `backend` (which would skip forwardAuth and the ban gate, or expose `/internal/*`). Ports 80/443 stay published for LAN workstations; the backend believes `CF-Connecting-IP` only when the peer Traefik saw is in `TUNNEL_PEER_CIDRS` (default that subnet), so direct hits on those ports cannot forge a client IP. Traefik also has an address in the subnet but is never its own peer. Firewall the ports from the internet if you have no workstations.

### Direct Mode (Let's Encrypt Wildcard)

For self-hosted on a static IP with direct domain control:

1. Set deployment mode:
   ```bash
   COMPOSE_PROFILES=direct
   DEPLOY_MODE=direct
   DOMAIN=your.domain.com
   LE_EMAIL=admin@your.domain.com
   ```

2. Configure DNS API credentials. Example for Cloudflare:
   ```bash
   CF_DNS_API_TOKEN=<your-cloudflare-api-token>
   ```
   See `traefik/traefik-direct.yml` for other DNS providers (Route53, DigitalOcean, etc.) — edit the ACME provider name and add environment variables as needed.

3. Start services:
   ```bash
   docker compose up -d
   ```

Traefik will automatically request and renew wildcard `*.your.domain.com` certificates from Let's Encrypt. Certificates are stored in the `letsencrypt` Docker volume.

## Backups

The `db-data` volume contains:
- **SQLite database** (`/app/data/styx-portal.db`) — templates, instances, users, OAuth providers
- **Mount backups** (`/app/data/mount-backups/<service-id>/<timestamp>/`) — copies of app settings files Styx saved before changing an app's base path (last 5 per service). Included in the data-volume backup below; see [Services](SERVICES.md#letting-styx-configure-an-app)
- **Secrets file** (`/app/data/secrets.json`, mode 0600) — JWT secret for signing tokens and deriving encryption keys

**Losing `secrets.json` logs out all users and invalidates stored OAuth client secrets.**

Backup strategy:
```bash
# Backup the entire data volume
docker run --rm -v db-data:/data -v $(pwd):/backup alpine tar czf /backup/db-data-$(date +%s).tar.gz -C /data .

# Or just secrets.json (minimum)
docker cp styx-backend:/app/data/secrets.json ./secrets.json.backup
```

For production, set up automated daily backups and test restore procedures.

## Security Posture

All of the following are already implemented:

- **Socket-proxy writes:** managed mounts write settings files with the Docker archive API, so the socket-proxy needs `POST=1` (set in `docker-compose.yml`). Exec, build and system calls stay blocked.
- **docker-socket-proxy:** Backend communicates through a socket-proxy that allows POST (needed for create, start, archive and network calls), so it is not read-only; direct socket access is denied. Dangerous operations (exec, build, system commands) are explicitly blocked.
- **Container isolation:** Instances run with `cap_drop: ["ALL"]` + minimal needed capabilities. DinD (Docker-in-Docker) templates are privileged, admin-only, and require memory/CPU limits.
- **No Traefik dashboard:** API dashboard is disabled (`api.insecure: false`). Optional opt-in via basicAuth environment variable (not enabled by default).
- **Refresh-token reuse detection:** RFC 9700 family-based rotation. Presenting a revoked token invalidates the entire family and logs an audit event.
- **Per-user instance networks:** Each user gets an isolated Docker bridge network (`styx-u-{user_id}`). Instance containers are confined to their user's network.
- **Security headers:** CSP, HSTS (direct mode only), X-Frame-Options, X-Content-Type-Options all enforced.
- **Audit log:** All auth, role, instance, and provider changes are logged to the audit table with timestamp, user, IP, and action. Accessible at `GET /api/audit` (admin).
- **Trusted proxies:** The backend believes `CF-Connecting-IP` / `X-Forwarded-For` only from peers in `TRUSTED_PROXY_CIDRS` (default `127.0.0.1/32,::1/128,172.16.0.0/12`, docker's default bridge pools). Widen it only if your docker `daemon.json` uses other address pools. `CF-Connecting-IP` is ignored in direct mode.
- **Proxied-service network:** Containers exposed as services join the `styx-services` network, shared only with Traefik (not the backend). forwardAuth checks run on `/internal/...`, a path no Traefik router exposes. Service health for these containers comes from the Docker API (container state / `HEALTHCHECK`), not HTTP.
- **Session cookie split:** `access_token` is scoped to `Path=/api` and `refresh_token` to `Path=/api/auth`, so proxied apps (same origin, other paths) never receive Styx API tokens. Proxied apps and workstation streams are gated by a separate `styx_proxy` cookie (`Path=/`, HttpOnly, SameSite=Strict) holding a `proxy`-type token that the API refuses and that dies with the refresh-token family (logout, password change, reuse detection, user deactivation). Old `Path=/` cookies are expired automatically on next login/refresh.
- **Instance desktops require login + ownership:** `/i/<subdomain>/` (and its extra ports) is gated by a per-instance forwardAuth `/internal/instances/<id>/auth-check` (the instance is bound by the route, never parsed from the request): a valid `styx_proxy` cookie and the instance's owner or an admin. Subdomains are user-chosen, so the URL is not a secret. Anonymous browser navigations are redirected to `/login?next=…` (XHR/websocket get 401), other users get 403, stopped/unknown instances show the unavailable page. Direct-mode extra ports on `<sub>.<domain>` only see the cookie if `COOKIE_DOMAIN` covers subdomains.
- **Safe `next=`:** Login redirects (SPA and every backend redirect builder) only follow same-site paths that do not start with `api`, `internal`, `_styx`, `login`, `logout`, `setup`, `accept-invite` or `change-password` (any case, after decoding) and contain no encoded `.`/`/`/`\` or dot segments, so a cross-site `/login?next=/api/...` link cannot become a same-site request carrying SameSite=Strict cookies.
- **Cookie strip:** Styx strips its cookies from every proxied request; upstream servers never see Styx credentials. Each forwardAuth (service auth-check, workstation auth-check, instance auth-check, a strip-only check for app-native services) returns the request's `Cookie` minus `styx_proxy`, `access_token`, `refresh_token`, `csrf_token` and `styx_svc`, and Traefik swaps it in via `authResponseHeaders`. App cookies pass through unchanged.

### Proxied apps are trusted code

The cookie split and strip stop an upstream **server** from capturing and replaying any Styx credential, and a stolen `styx_proxy` cookie cannot call the API. They do **not** isolate an app's **JavaScript**: a proxied app is still same-origin, so its scripts (which can't read HttpOnly cookies) can call `/api/...` through the user's browser with that user's full Styx rights (the browser attaches the `/api` cookies; `HttpOnly` only prevents reading them).

- Only proxy apps you would trust with the viewing user's Styx account.
- Admins: use a separate **non-admin** account for day-to-day app use; keep the admin account for administration.
- Prefer apps from trusted sources and keep them patched; an XSS in a proxied app is an XSS in Styx.

## Health Monitoring

### Diagnostics Endpoint

Check system health via API:
```bash
curl -H "Cookie: auth_token=<your-token>" \
  https://your.domain.com/api/system/diagnostics
```

Returns Docker engine version, database writability, Traefik routes status, disk usage, and GPU availability. Each check includes latency (ms) and a detail string.

### Health Page (Admin UI)

Admins navigate to **System → Settings → Health** to view:
- Status of each diagnostic check (Docker, DB, routes, disk, GPU)
- Latency (milliseconds) for each check
- Status history over the last 24 hours
- Manual "Run checks" button for on-demand diagnostics

## Host-Level Setup Gates

The following must be configured on the Docker host (not in the container):

### GPU Support

If you plan to use GPU, set these on the host BEFORE starting the portal:
```bash
# Find the numeric GIDs
getent group video render

# Set in .env (example values, replace with your host's GIDs)
VIDEO_GID=44
RENDER_GID=992
```

Wrong GID values won't cause the portal to fail, but GPU won't be accessible until corrected. See [docs/GPU.md](GPU.md) for more details.

### Desktop Template Capabilities

If a desktop template fails to boot when confined (cap_drop ALL), the operator may add minimal `cap_add` to the template spec (admin UI). Start with an empty list; add capabilities only if empirically needed.

## Instance Quotas

Limit concurrent instances per non-admin user:
```bash
MAX_INSTANCES_PER_USER=3  # 0 = unlimited; admins exempt
```

Set in `.env` before first start. Admins are always exempt from the quota.

## Upgrades

Database migrations run automatically on boot. Simply `docker compose down && docker compose up -d` with a new version; the backend will apply any pending migrations.

### Hosted images & pinning

The `backend` and `frontend` images are published to GHCR (`ghcr.io/sgtslaughta/styx-backend`, `…/styx-frontend`) on every release. For production, **pin a tag** rather than tracking `latest` so deploys are reproducible:

```bash
# .env
STYX_TAG=1.0.0          # pin the release
# REGISTRY=ghcr.io/sgtslaughta   # override the namespace if you mirror it

docker compose pull && docker compose up -d
```

Upgrade by bumping `STYX_TAG` to the new release and re-running `pull && up -d`. To roll back, set `STYX_TAG` to the previous version. If the GHCR packages are private, `docker login ghcr.io` (or set the package visibility to public). The desktop instance image is published as `ghcr.io/sgtslaughta/styx-desktop` for use in templates.

## Monitoring Checklist

- [ ] Secrets file backed up outside the host
- [ ] Daily data-volume backups configured
- [ ] Health page confirms all checks green
- [ ] Audit log reviewed for anomalies (malicious role changes, mass instance creation)
- [ ] `COOKIE_SECURE=true` set in `.env` (production only)
- [ ] JWT_SECRET is ≥32 random characters (or auto-generated and backed up)
- [ ] DinD templates (if used) have memory/CPU limits
- [ ] GPU GIDs correct if GPU instances are enabled
- [ ] TLS certificates auto-renewing (direct mode: check letsencrypt volume for recent `acme.json`)
