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

- **docker-socket-proxy:** Backend communicates with a read-only socket-proxy; direct socket access is denied. Dangerous operations (exec, build, system commands) are explicitly blocked.
- **Container isolation:** Instances run with `cap_drop: ["ALL"]` + minimal needed capabilities. DinD (Docker-in-Docker) templates are privileged, admin-only, and require memory/CPU limits.
- **No Traefik dashboard:** API dashboard is disabled (`api.insecure: false`). Optional opt-in via basicAuth environment variable (not enabled by default).
- **Refresh-token reuse detection:** RFC 9700 family-based rotation. Presenting a revoked token invalidates the entire family and logs an audit event.
- **Per-user instance networks:** Each user gets an isolated Docker bridge network (`styx-u-{user_id}`). Instance containers are confined to their user's network.
- **Security headers:** CSP, HSTS (direct mode only), X-Frame-Options, X-Content-Type-Options all enforced.
- **Audit log:** All auth, role, instance, and provider changes are logged to the audit table with timestamp, user, IP, and action. Accessible at `GET /api/audit` (admin).

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
