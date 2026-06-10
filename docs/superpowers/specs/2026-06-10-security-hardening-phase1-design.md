# Security Hardening — Phase 1 Design

Date: 2026-06-10
Status: Approved (user, 2026-06-10)
Scope: Phase 1 of 3. Phase 2 = UI polish, Phase 3 = onboarding/diagnostics (separate specs).

## Goal

Secure-by-default deployment: a beginner running `docker compose up` gets a hardened
system with zero manual secret handling; power users keep template-level overrides.
Close the authorization, token, and container-isolation gaps found in the 2026-06-09
security audit.

## Decisions (user-approved)

1. **TLS model:** support both Cloudflare Tunnel (current, default) and direct
   Let's Encrypt — selected via `DEPLOY_MODE`.
2. **Secrets:** auto-generate `JWT_SECRET` on first run, persist to data volume.
3. **Isolation:** harden container defaults (seccomp/apparmor/caps/per-user networks
   + socket proxy); DinD stays privileged, admin-only, opt-in. No Sysbox.
4. **Account linking:** always require verified email (ignore `trust_email` for linking).
5. **IdP admin auto-promotion:** keep, but audit-log it and add per-provider
   `auto_promote_admins` toggle (default true for back-compat).

## 1. Secrets auto-generation

`backend/app/config.py`

- If `JWT_SECRET` env unset: load or create `/app/data/secrets.json` (mode 0600)
  containing `{"jwt_secret": "<secrets.token_urlsafe(48)>"}`. Log one WARNING when
  generated. Env var always wins over file.
- If set: enforce ≥32 chars; reject known placeholder value
  `change-me-to-a-long-random-string-min-32-bytes` with a clear startup error that
  includes the `openssl rand -base64 48` command.
- Remove the `dev-insecure-secret-do-not-use-in-prod` fallback entirely. Dev mode
  (`COOKIE_SECURE=false`) also uses the generated persistent secret.
- Fernet key stays HKDF(JWT_SECRET) — document that rotating JWT_SECRET invalidates
  stored OAuth client secrets (re-entry required).

## 2. TLS / deployment mode

- New env `DEPLOY_MODE=tunnel|direct` (default `tunnel` — current behavior).
- **tunnel:** unchanged topology (cloudflared → traefik inside the compose network,
  no host ports). TLS terminates at Cloudflare edge.
- **direct:** compose profile `direct` adds host ports 80/443 on traefik plus a
  second static config `traefik/traefik-direct.yml`:
  - `websecure` entrypoint :443, `web` :80 with HTTP→HTTPS redirect
  - ACME DNS-01 resolver (wildcard `*.{DOMAIN}` + `{DOMAIN}`), provider + creds via
    env (`LE_DNS_PROVIDER`, provider-specific vars), storage on a named volume
  - `cloudflared` service moves under a `tunnel` profile so it only starts in
    tunnel mode
- Traefik dashboard: `api.insecure: false` in both modes. Optional opt-in route
  behind basicAuth middleware (`TRAEFIK_DASHBOARD_AUTH` htpasswd hash env); absent
  → no dashboard router.
- `route_writer.py`: drop the blanket `insecureSkipVerify: true` serversTransport.
  Add per-template boolean `tls_skip_verify` (default false) for images that serve
  self-signed HTTPS internally (e.g. Selkies); only those services reference the
  insecure transport. Existing seed templates that need it set it explicitly.

## 3. Docker socket proxy

`docker-compose.yml`

- New service `docker-proxy` (`lscr.io/linuxserver/socket-proxy` or
  `tecnativa/docker-socket-proxy`), socket mounted **read-only into proxy only**,
  attached to an internal-only network `styx-docker` shared with backend.
- Allow: `CONTAINERS=1 IMAGES=1 NETWORKS=1 VOLUMES=1 POST=1 INFO=1 EVENTS=1 PING=1`.
  Deny (default 0): exec, build, commit, swarm, system, secrets, configs, plugins.
- Backend loses the socket mount; `DOCKER_SOCKET=tcp://docker-proxy:2375`.
  `docker_manager.py` already takes the URL from settings — verify
  `DockerClient(base_url=...)` path works for tcp and screenshots/stats still work.
- Caveat: container `attach`/`logs` streaming over the proxy must be verified;
  if a feature needs a denied endpoint, allow that endpoint explicitly rather than
  reverting to direct socket.

## 4. Container isolation

`backend/app/services/docker_manager.py`

- Remove default `security_opt: ["seccomp=unconfined", "apparmor=unconfined"]`.
  New defaults for non-privileged containers:
  - `security_opt: ["no-new-privileges:true"]` (runtime default seccomp/apparmor)
  - `cap_drop: ["ALL"]` + vetted desktop cap set via template
- New template fields (power-user overrides, admin-only to set):
  - `cap_add: list[str]` (default `[]`)
  - `security_opt: list[str]` (default `[]`, appended)
  - `tls_skip_verify: bool` (see §2)
  - Seed Selkies desktop templates get the minimal cap set verified to boot the
    desktop (determine empirically during implementation; start from `[]` and add).
- **Per-user networks:** instance containers join `styx-u-{user_id[:12]}` (bridge,
  created lazily by backend via proxy). Traefik must reach instance containers:
  backend connects the traefik container to each user network on first instance
  create (and disconnects when a user's last instance is removed). Backend itself
  stays off user networks.
- **DinD:** unchanged privileged path, admin-only (already enforced), but:
  mandatory `mem_limit`/`cpus` from template (reject DinD template without limits),
  audit-logged on create.
- **Quotas:** `max_instances_per_user` setting (default 3, `0` = unlimited; admins
  exempt). Enforced in `create_instance`. Per-user rate limit on instance create
  (reuse SlidingWindow, e.g. 10/hour keyed by user id).

## 5. Auth / authorization fixes

- **CSRF:** remove `/api/auth/refresh` and `/api/auth/accept-invite` from the CSRF
  exempt list (`main.py`). Frontend `api.ts` must send the CSRF header on both.
  Accept-invite page loads CSRF cookie via existing bootstrap (verify; if the
  anonymous CSRF cookie isn't issued yet, issue one on GET of invite metadata).
- **Refresh-token reuse detection (RFC 9700):** add `family_id` to refresh-token
  records. Rotation keeps family; presenting a revoked/rotated token revokes the
  entire family and audit-logs `token_reuse_detected`.
- **Account linking:** `link_identity()` requires `identity.email_verified` always;
  `trust_email` applies to login/signup resolution only.
- **Subdomain validation:** schema-level validator
  `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$` on instance create/update; also reject
  reserved names (`traefik`, `api`, `www`, the portal host). Closes Traefik label
  injection.
- **Shared templates:** `owner_id IS NULL` → modify/delete requires admin
  (`templates.py` update + delete paths).
- **IdP promotion:** `OAuthProvider.auto_promote_admins: bool = True`; when false,
  matching admin group logs `admin_claim_pending` instead of elevating. Elevation
  (when true) writes an audit event.
- **Audit log:** new table

  ```python
  class AuditLog(SQLModel, table=True):
      id: int | None = Field(default=None, primary_key=True)
      ts: datetime  # UTC
      user_id: str | None
      actor_ip: str | None
      action: str          # e.g. "auth.login", "auth.refresh_reuse", "user.role_change",
                           # "sso.link", "provider.update", "instance.create", "instance.delete"
      resource: str | None # resource id
      detail: str | None   # JSON blob, secrets redacted
  ```

  Helper `audit(session, request, action, ...)`. Events: login success/fail,
  logout, refresh reuse, SSO link/unlink, signup, role change (manual + IdP),
  provider CRUD, user disable/enable, invite create/accept, instance
  create/delete, DinD launch. Read API: `GET /api/audit` (admin, paginated).
  UI viewer deferred to Phase 2.

## 6. Infra hygiene

- Backend Dockerfile: create uid-1000 user, `USER appuser`; volumes chowned;
  `/dev/dri` access via `video`/`render` group-add.
- SQLite file chmod 0600 after init (`database.py`).
- Compose healthchecks: backend (`GET /api/health`), traefik (`traefik healthcheck
  --ping`, enable ping endpoint), frontend (nginx `wget` localhost), docker-proxy.
- Frontend `nginx.conf`: add X-Content-Type-Options, X-Frame-Options DENY,
  Referrer-Policy, Permissions-Policy, CSP mirroring backend policy. (HSTS only in
  direct mode — set at Traefik middleware level instead of nginx to avoid breaking
  tunnel-mode local access.)
- CORS: include `http://localhost:5173` only when `COOKIE_SECURE=false`.
- `database.py` migrations: stop swallowing all exceptions — ignore
  "duplicate column" only, log + raise the rest.
- Mass-assignment guard: instance/template PATCH applies an explicit allowed-field
  set instead of raw `model_dump` iteration.

## Out of scope (Phase 1)

- Audit log UI, session-expiry warning UX, idle countdown (Phase 2)
- Diagnostics endpoint/Health page, setup-wizard config validation, docs split,
  GPU guide, pull progress (Phase 3)
- Sysbox/gVisor, secret rotation tooling, per-instance resource limit UI

## Testing

- Unit: secret generation/persistence/validation; subdomain validator; quota +
  rate-limit; CSRF on refresh/accept-invite; refresh reuse → family revocation;
  link requires verified email; shared-template admin gate; audit rows written;
  migration error surfacing.
- Docker manager (mocked): security_opt/cap defaults, per-user network arg,
  DinD limit enforcement, tcp base_url.
- Manual smoke (documented in plan): tunnel mode boot, direct mode boot with LE
  staging, instance launch end-to-end through socket proxy, desktop usable with
  hardened caps, Traefik reaches instance on per-user network.

## Risks

- **Cap hardening may break Selkies desktops** — mitigate empirically: boot seed
  templates, add minimal caps, document final set in template JSON.
- **Socket proxy may block a needed endpoint** (stats/attach/logs) — verify each
  docker_manager call path; allow specific endpoints, never the socket.
- **Per-user networks + Traefik connectivity** — requires connecting traefik
  container to user networks at runtime; test create/destroy churn.
- **CSRF on refresh** — ensure frontend silent-refresh path sends header; breakage
  logs users out rather than failing open (acceptable).
- **JWT_SECRET file on volume** — back-compat: existing deployments with env set
  see no change.
