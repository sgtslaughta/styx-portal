# Service Proxy Core (SP1) — Design

Date: 2026-10-12
Status: draft for review
Program: Unified Remote Access (SP1 of 4)

## 1. Program context

Styx becomes a unified remote-access gateway. One whitelisted hostname
(`g.jmolabs.dev`, via Cloudflare Tunnel) proxies any internal HTTP service:
containers on the Styx host, containers on other LAN docker hosts, anything
reachable at `ip:port`. Admins add and configure services in the Styx UI.
Access is multi-user and group-based. The deployment is internet-exposed,
so security wins over convenience and every risk is spelled out in the UI
and the docs.

Hard constraints:

- **One hostname.** No subdomains, no wildcards (corporate allowlist).
  Everything is path-multiplexed on the single host.
- **No HTML/JS rewriting.** Apps either support a base URL (`path` mode) or
  take over the root via a routing cookie (`cookie-root` mode).
- **HTTP(S) only.** No raw TCP/UDP.
- **All traffic CF → Traefik → Styx host → internal host.** No LAN bypass.

Sub-projects, each with its own spec and plan:

| # | Sub-project | Summary |
|---|-------------|---------|
| SP1 | Service proxy core (this spec) | `proxied_services` + groups, route_writer modes, Styx-side auth-check, local docker discovery, health, UI, presets |
| SP2 | Authentik SSO | compose profile (server/worker/postgres/redis), path-multiplexed on the same host, bootstrap + auto-provisioning, Styx login via Authentik OIDC, domain-level forwardAuth chained to Styx auth-check, external-Authentik option |
| SP3 | Remote docker hosts | SSH docker contexts (`ssh://user@host`, key Fernet-encrypted), discovery on remote hosts |
| SP4 | Deploy from template | service presets gain a `deploy` block; Styx launches the app container itself and sets its base URL |

SP1 is useful standalone with current Styx native auth. SP2 swaps identity
underneath without changing SP1's routing or ACL model.

## 2. Verified facts

- Styx reserves `/api`, `/i/`, `/w/`, `/assets`, `/login`, `/setup`,
  `/connecting`, `/change-password`, `/accept-invite`.
- Authentik serves only namespaced prefixes: `/if/`, `/api/v3/`,
  `/application/`, `/outpost.goauthentik.io/`, `/static/`, `/media/`,
  `/flows/`, `/ws/`, `/-/`, `/.well-known/`, `/source/`. None collide with
  Styx. SP1 reserves them now so SP2 needs no slug migration.
- `route_writer.build_routes_config` already emits Host-scoped routers with
  priorities (`/api` 100, workstations 50, frontend 1), shared middlewares
  `ip-ban-gate`, `styx-ratelimit`, and a forwardAuth pattern
  (`/api/workstations/auth-check`).
- `docker-proxy` (linuxserver socket-proxy) already allows
  `CONTAINERS=1 NETWORKS=1 POST=1`, enough to list containers and connect
  them to a network.
- `audit_log` table exists. Users have `role` (`admin|user`) only; no groups.

## 3. Data model

### 3.1 `proxied_services`

| column | type | notes |
|--------|------|-------|
| id | int pk | |
| slug | str unique | URL-safe, validated against reserved list (§4.5) |
| name | str | display |
| icon | str | optional, preset-provided or URL |
| kind | `url` \| `docker-local` | |
| upstream_url | str | `url` kind: `http(s)://host:port[/base]` |
| container | str | `docker-local` kind: container name/id |
| container_port | int | `docker-local` kind |
| mount_mode | `path` \| `cookie-root` | |
| auth_mode | `sso` \| `sso-with-bypass` \| `app-native` | |
| bypass_rules | JSON | `[{"path_prefix": str, "required_header": str\|null}]` |
| allowed_groups | JSON | list of group names; empty = any logged-in user |
| verify_tls | bool | default true |
| health_path | str | optional, relative to upstream |
| health_status | `healthy` \| `unhealthy` \| `unknown` | written by health loop |
| health_checked_at | datetime | |
| preset_id | str | optional, which preset seeded it |
| enabled | bool | disabled = no routes emitted, tile hidden |
| created_at / updated_at | datetime | |

`host` mount mode is deliberately absent (one-hostname rule).

### 3.2 `groups`, `user_groups`

- `groups`: `id`, `name` unique, `description`.
- `user_groups`: `user_id`, `group_id` composite pk.
- SP2 overwrites a user's memberships from the Authentik groups claim on
  each login; Styx becomes a cache, Authentik the source of truth.

### 3.3 Service presets

JSON files in `templates/services/*.json`, seeded into a `service_presets`
table on startup (same pattern as instance templates). Fields: `id`, `name`,
`icon`, `default_port`, `mount_mode`, `auth_mode`, `bypass_rules`,
`health_path`, `verify_tls`, `base_url_hint` (human instructions for the
app's base-URL setting), `warnings` (list of strings shown in the UI).

v1 presets:

| preset | mode | auth | bypass | notes |
|--------|------|------|--------|-------|
| sonarr / radarr / prowlarr / lidarr | path | sso-with-bypass | `/<slug>/api` + `X-Api-Key` | hint: `UrlBase=/<slug>` |
| jellyfin | path | sso-with-bypass | `/<slug>/` + `Authorization` (MediaBrowser token) | hint: base URL `/<slug>` |
| nextcloud | path | sso | — | hint: `overwritewebroot` |
| gitlab | path | sso | — | hint: `relative_url_root` |
| audiobookshelf | cookie-root | sso-with-bypass | `/api` + `Authorization` | no subpath support upstream |
| unraid | cookie-root | sso | — | `verify_tls=false`, warning |
| generic-url | path | sso | — | blank |

## 4. Routing (route_writer extension)

All service routers are `Host(<domain>) && ...`, get `ip-ban-gate` and
`styx-ratelimit`, and a per-service `svc-auth-<slug>` forwardAuth
(omitted for `app-native`). Disabled services emit nothing.

### 4.1 `path` mode

- Rule: `Path(`/<slug>`) || PathPrefix(`/<slug>/`)` (segment boundary), priority 60. No StripPrefix: the app is
  configured with its base URL and expects the prefix.

### 4.2 `cookie-root` mode

- Rule: `HeaderRegexp(`Cookie`, `styx_svc=<slug>`)`, priority 40.
  Catches `/` and everything the app serves. Sits above the frontend
  router (1) and below `/api` (100), `/i/`, `/w/`, and Authentik prefixes.
- Styx frontend sends `X-Styx-Client: 1` on every API request (one line in
  the fetch wrapper). When at least one cookie-root service exists, the
  `/api` router rule becomes
  `PathPrefix(`/api`) && Header(`X-Styx-Client`, `1`)` so Styx's own API
  keeps working while the cookie is set, and the app's `/api` reaches the
  app.
- Entering: the Styx tile calls `POST /api/services/<slug>/enter` through
  the frontend fetch wrapper (so the `X-Styx-Client` header and CSRF token
  are present even if another takeover cookie is already set). Backend
  checks the ACL, sets `styx_svc=<slug>; Path=/; Secure; HttpOnly;
  SameSite=Lax`, and the frontend then navigates to `/`.
- Escape hatch: `GET /_styx/exit` (backend route, Traefik priority 90)
  clears the cookie and redirects to `/`. While the cookie is set the portal
  itself is not reachable, so there is no in-portal banner; the tile tooltip
  and the docs name `/_styx/exit`, and the unavailable page links to it.
- Limits (documented, shown in UI): one cookie-root service active per
  browser; browser-only (mobile apps cannot set the cookie).

### 4.3 Middlewares per service

- `svc-auth-<slug>`: forwardAuth to
  `http://backend:8000/api/services/<slug>/auth-check`, `trustForwardHeader`
  false, `authResponseHeaders: [X-Styx-User, X-Styx-Groups]`.
- `styx-strip-identity` (shared): headers middleware
  that deletes client-supplied `X-Styx-*` and `X-authentik-*` request
  headers before forwardAuth runs. Spoof-proof.
- Unavailable upstream: Traefik `errors` middleware on 502/503/504 →
  `/api/service-unavailable?slug=<slug>` (reuses the instance-unavailable
  page pattern).

### 4.4 Upstream transport

- `url` kind: Traefik service `loadBalancer.servers[0].url = upstream_url`.
  `verify_tls=false` emits a per-service `serversTransport` with
  `insecureSkipVerify: true`.
- `docker-local` kind: on create/enable, backend connects the container to
  the `styx-portal` network via docker-proxy; upstream is
  `http://<container>:<container_port>`. If the connect fails (e.g.
  `network_mode: host`), fall back to `http://host.docker.internal:<published
  port>` and record the fallback in the service row.

### 4.5 Reserved slugs

Rejected at create/update (400 with explanation):

`api i w assets login setup connecting change-password accept-invite _styx`
plus Authentik: `if application outpost.goauthentik.io static media flows
ws - .well-known source` (and the `api/v3` prefix is covered by `api`).

## 5. Auth-check endpoint

`GET /api/services/{slug}/auth-check` — called by Traefik forwardAuth with
`X-Forwarded-Uri`, `X-Forwarded-Method`, and the original cookies/headers.

Order:

1. Service missing or disabled → 404.
2. `auth_mode == sso-with-bypass` and a bypass rule matches: `X-Forwarded-Uri`
   starts with `path_prefix` AND (`required_header` is null OR that header is
   present, any value) → 200. Nothing else is checked.
3. No valid Styx session cookie → 302 to `/login?next=<X-Forwarded-Uri>`.
4. Session valid → admin always 200. Otherwise user must be in at least one
   of `allowed_groups` (empty list = any user) → 200, else 403 rendered by
   the Styx "no access" page.
5. On 200, respond with `X-Styx-User: <username>` and
   `X-Styx-Groups: a,b` (SP2 adds `X-authentik-*` passthrough).

Rate limit and ban gate run in Traefik before this endpoint.

## 6. Discovery

`GET /api/services/discover` (admin): lists running local containers via
docker-proxy with name, image, exposed ports, networks. Excludes containers
Styx launched (instance label) and the Styx stack itself (compose project
label). UI "Add from container" prefills `kind=docker-local`, container,
port, and suggests a preset by image name match.

## 7. Health loop

Background task (same shape as `session_monitor`): every 30s, for each
enabled service with `health_path`, GET `<upstream><health_path>` with a
5s timeout, honoring `verify_tls`. 2xx/3xx → `healthy`, else `unhealthy`.
Without `health_path` → `unknown`. Tiles show a dot; unhealthy tiles stay
clickable.

## 8. API surface

Admin-only unless noted. All mutations write `audit_log`.

| method | path | notes |
|--------|------|-------|
| GET | `/api/services` | any user; filtered to services the caller may open; includes health |
| POST | `/api/services` | create; validates slug, mode/auth combo, bypass rules |
| PUT | `/api/services/{id}` | update |
| DELETE | `/api/services/{id}` | delete, disconnect container from network if we connected it |
| POST | `/api/services/{id}/enable` / `disable` | |
| GET | `/api/services/discover` | §6 |
| GET | `/api/services/presets` | seeded presets |
| POST | `/api/services/{slug}/enter` | any user; cookie-root entry, checks ACL first |
| GET | `/_styx/exit` | any; clears cookie |
| GET | `/api/services/{slug}/auth-check` | Traefik only (internal network), §5 |
| GET | `/api/groups`, POST, PUT, DELETE | groups CRUD |
| GET, PUT | `/api/users/{id}/groups` | read / set memberships |

Every write triggers `route_writer.write_routes` (extend signature with
`services=`), same as instances/workstations.

## 9. UI

- **Home:** new "Services" tile section, filtered by the caller's groups,
  with health dot. Path-mode tile opens `/<slug>` in a new tab;
  cookie-root tile calls `enter` and opens `/`.
- **Admin → Services:** table (name, slug, mode, auth, health, enabled).
  Add/edit drawer: preset picker, "Add from container" discovery picker,
  kind fields, mount mode, auth mode, bypass rule editor, allowed groups
  multi-select, `verify_tls` toggle, `health_path`, base-URL hint shown
  read-only from preset.
- **Admin → Users → Groups:** groups CRUD, per-user group multi-select.
- **Risk messaging (required, not optional):**
  - Each bypass rule: red callout "Requests matching `<prefix>` are
    reachable from the internet WITHOUT Styx login. Only the app's own
    credential and rate limiting protect them."
  - `app-native`: callout "Styx does not authenticate this service. The app
    must enforce its own login."
  - `verify_tls=false`: callout "Upstream certificate is not verified.
    Traffic between Styx and this host can be intercepted on your LAN."
  - `cookie-root`: callout "Takes over the root of the hostname for this
    browser. One service at a time. Mobile apps cannot use this mode."
- **Docs:** new page `docs/security-model.md` section "Proxied services":
  exposure model, the three auth modes, bypass risk, cookie-root mechanics
  and escape hatch, TLS verification, what is and is not protected by
  Styx. Linked from every callout.

## 10. Security summary

- Internet-exposed by design; every service router carries
  `ip-ban-gate` + `styx-ratelimit`.
- Identity headers are stripped from client requests before forwardAuth.
- Bypass rules are the only unauthenticated surface and require an explicit
  admin opt-in per rule with a red warning; `required_header` filters
  scanners but is not authentication.
- The routing cookie is a selector, never a credential; ACL is enforced on
  every request by `auth-check`, not at `enter` time only.
- `auth-check` is only reachable on the internal docker network (Traefik →
  backend); it is not routed publicly.
- Secrets introduced later (SSH keys, Authentik token) use the existing
  Fernet pattern. SP1 stores no new secrets.
- Admin-only CRUD, every mutation audited.

## 11. Testing

- `route_writer`: one test per mount mode, priority ordering, `/api`
  header gating toggles only when a cookie-root service exists, reserved
  slug rejection, `verify_tls=false` transport, disabled service emits
  nothing.
- `auth-check`: bypass match with/without header, anonymous redirect,
  group allow/deny, admin override, disabled service 404.
- Discovery with mocked docker client; Styx-managed containers excluded.
- Health loop state transitions with mocked HTTP.
- Groups CRUD and membership.
- Gates: full pytest suite green, `ruff check`, frontend `npm run build`.

## 12. Out of scope (later SPs)

Authentik, remote docker hosts, deploy-from-template, TCP/UDP, host
mount mode, HTML rewriting, upstream cert pinning, upstream basic-auth
injection, LAN direct connect.
