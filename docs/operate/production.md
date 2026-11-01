# Production

A hardened checklist: TLS, backups, upgrades and the security posture you get by default.

## TLS

### Cloudflare Tunnel (default)

```bash
COMPOSE_PROFILES=tunnel
DEPLOY_MODE=tunnel
DOMAIN=styx.example.com
CF_TUNNEL_TOKEN=<your-token>
```

TLS terminates at Cloudflare's edge. The Traefik dashboard is off.

**Tunnel origin:** the tunnel's public hostname must point at `http://styx-traefik:80`. cloudflared shares only the dedicated `styx-tunnel` network with Traefik (`172.31.254.0/28`; set `STYX_TUNNEL_SUBNET` if it clashes) and cannot reach `frontend` or `backend`, which would skip forwardAuth and the ban gate or expose `/internal/*`. Ports 80/443 stay published for LAN workstations. The backend believes `CF-Connecting-IP` only when the peer Traefik saw is in that subnet (compose passes it as `TUNNEL_PEER_CIDRS`), so direct hits on those ports cannot forge a client IP. Firewall the ports from the internet if you have no workstations.

### Direct mode (Let's Encrypt wildcard)

For a static IP and DNS control:

```bash
COMPOSE_PROFILES=direct
DEPLOY_MODE=direct
DOMAIN=styx.example.com
LE_EMAIL=admin@styx.example.com
CF_DNS_API_TOKEN=<your-cloudflare-api-token>
```

For other DNS providers (Route53, DigitalOcean, ...) edit the ACME provider name in `traefik/traefik-direct.yml` and add the matching environment variables. Then `docker compose up -d`. Traefik requests and renews `*.styx.example.com` and stores certificates in the `letsencrypt` volume. `CF-Connecting-IP` is ignored in direct mode.

## Backups

The `db-data` volume holds:

- the SQLite database `/app/data/styx-portal.db` (templates, instances, users, OAuth providers);
- mount backups `/app/data/mount-backups/<service-id>/<timestamp>/` (last 5 per service; see [Proxied services](services.md#backups-and-rollback));
- `secrets.json` (mode 0600): the JWT secret and the root of the encryption keys.

```bash
# Whole volume
docker run --rm -v db-data:/data -v $(pwd):/backup alpine tar czf /backup/db-data-$(date +%s).tar.gz -C /data .

# Minimum: the secrets file
docker cp styx-backend:/app/data/secrets.json ./secrets.json.backup
```

Automate daily backups and test a restore.

## Hosted images and pinning

The `backend` and `frontend` images are published to GHCR (`ghcr.io/jmo-labs/styx-backend`, `styx-frontend`). Pin a tag in production:

```bash
# .env
STYX_TAG=2.7.0
docker compose pull && docker compose up -d
```

See [Upgrade](upgrade.md). The desktop image is published as `ghcr.io/jmo-labs/styx-desktop` for use in templates.

## Host-level gates

- **GPU:** set `VIDEO_GID` and `RENDER_GID` before first start ([GPU](gpu.md)). Wrong values still boot.
- **Desktop capabilities:** if a desktop template fails to boot under `cap_drop: ALL`, add the minimal `cap_add` in the template editor ([Templates and instances](templates-instances.md#admin-only-fields)).
- **Quotas:** `MAX_INSTANCES_PER_USER` (0 = unlimited, admins exempt), or live in [Settings](settings.md).

## Security posture

Everything below is already in place. Details and rationale are in [Security](security.md).

- Docker socket-proxy: POST allowed (create, start, archive, network) but exec, build and system calls blocked; no direct socket access.
- Instances run with `cap_drop: ["ALL"]` plus minimal capabilities; DinD templates are privileged, admin-only and need limits.
- Traefik dashboard off; `/docs`, `/redoc`, `/openapi.json` off unless `ENABLE_DOCS=true`; server banners off.
- Refresh-token reuse detection (RFC 9700), per-user instance networks, CSP/HSTS/X-Frame-Options/X-Content-Type-Options.
- Cookie split and strip so proxied upstreams never see Styx credentials.
- Audit log of auth, role, instance and provider changes.

## Production checklist

- [ ] `secrets.json` backed up off the host
- [ ] Daily data-volume backups and a tested restore
- [ ] Health page all green ([Monitoring](monitoring.md))
- [ ] Audit log reviewed for odd role changes or mass instance creation
- [ ] `COOKIE_SECURE=true`
- [ ] `JWT_SECRET` at least 32 random characters (or auto-generated and backed up)
- [ ] DinD templates (if any) have memory and CPU limits
- [ ] GPU GIDs correct (if GPU instances are enabled)
- [ ] Image tag pinned (`STYX_TAG`)
- [ ] Direct mode: `acme.json` in the `letsencrypt` volume is renewing
