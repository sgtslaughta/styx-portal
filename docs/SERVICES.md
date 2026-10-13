# Proxied Services

Styx can proxy any internal HTTP service (Jellyfin, the *arr stack, Nextcloud, GitLab,
Unraid, Audiobookshelf, anything at `ip:port`) through the single Styx hostname.
Admins add services under **Settings → Administration → Services**; users see tiles
on the home page for the services their groups allow.

## One hostname, two mount modes

- **Path** (`https://<host>/<slug>`): the app must be configured with that base URL
  (each preset shows the exact setting). Works in browsers and mobile apps. The Traefik
  rule is `Path(/slug) || PathPrefix(/slug/)`, so a slug never captures a sibling prefix
  (`son` does not match `/sonarr`).
- **Cookie root**: for apps with no base-URL support. Clicking the tile sets a routing
  cookie (`styx_svc`) and the app takes over `/` for that browser, including `/login`.
  One cookie-root service at a time; mobile apps cannot use this mode. To get back to
  Styx, open `https://<host>/_styx/exit`.

Slugs are validated on create/update. Reserved: `api i w assets login setup connecting
change-password accept-invite _styx`, plus Authentik paths (`if application
outpost.goauthentik.io static media flows ws - .well-known source`).

## Auth modes

| mode | who can reach it | use for |
|---|---|---|
| `sso` | logged-in Styx users in the allowed groups | browser-only apps |
| `sso-with-bypass` | as above, plus unauthenticated requests matching a bypass rule | apps with mobile clients / API keys |
| `app-native` | anyone on the internet; the app enforces its own login | apps with their own SSO |

### Bypass rules

A rule is a path prefix plus an optional required header name. A request bypasses Styx
login only when the normalised path matches the prefix on a **segment boundary**
(`/sonarr/api` matches `/sonarr/api/v3` but not `/sonarr/apix`) and, if set, the header is
present (any value). Requests containing `..` segments, backslashes or encoded `.`, `/`
or `\` (raw or decoded) are never eligible for bypass.

The header check only filters scanners: anyone can add a header. Only the app's own
credential (API key, token) protects bypassed requests.

## Groups

Create groups under Administration → Groups, assign users, then pick allowed groups on a
service by **name**. Empty allowed-groups means every logged-in user. Admins can always
open everything. Unknown group names are rejected (422). Deleting a group removes it from
every service; a service left with no groups is **disabled** (fail closed, since an empty
list would otherwise mean "any user").

## Discovery and health

"Add from container" lists running containers on the Styx host (excluding Styx's own stack
and launched instances). Adding one attaches it to the `styx-services` network
(`SERVICES_NETWORK`), which only Traefik shares; the backend and frontend are not on it.
If attaching fails (e.g. `network_mode: host`), Styx falls back to
`host.docker.internal:<port>` and shows a *fallback* badge (the port must be published on
the host). Changing or deleting the service disconnects the container unless another
service still uses it.

Health dots:

- **docker-local**: from Docker container state. Running is healthy unless a Docker
  `HEALTHCHECK` says otherwise (`starting` shows unknown); stopped or missing is unhealthy;
  Docker unreachable is unknown.
- **URL services**: an HTTP probe of `health_path` every 30 s (5 s timeout, honours
  verify-TLS, redirects are not followed). 2xx/3xx is healthy. Link-local and cloud
  metadata targets (e.g. `169.254.169.254`) are refused.

Unhealthy tiles stay clickable.

## Presets

Defined in `templates/services/*.json` and seeded on startup.

| preset | mount | auth | base URL setting |
|---|---|---|---|
| Sonarr | path | sso-with-bypass (`/sonarr/api` + `X-Api-Key`) | Settings → General → URL Base = `/sonarr` |
| Radarr | path | sso-with-bypass (`/radarr/api` + `X-Api-Key`) | URL Base = `/radarr` |
| Prowlarr | path | sso-with-bypass (`/prowlarr/api` + `X-Api-Key`) | URL Base = `/prowlarr` |
| Lidarr | path | sso-with-bypass (`/lidarr/api` + `X-Api-Key`) | URL Base = `/lidarr` |
| Jellyfin | path | sso-with-bypass (`/jellyfin/` + `Authorization`) | Dashboard → Networking → Base URL = `/jellyfin` |
| Nextcloud | path | sso | `config.php`: `overwritewebroot` = `/nextcloud`, `overwrite.cli.url` = `https://<host>/nextcloud` |
| GitLab | path | sso | `gitlab.rb`: `external_url 'https://<host>/gitlab'`, then reconfigure. CLI git over HTTPS will not pass SSO; use SSH remotes |
| Audiobookshelf | cookie-root | sso-with-bypass (`/api/` + `Authorization`) | none (no subpath support) |
| Unraid | cookie-root | sso, verify TLS off | none (self-signed certificate) |
| Generic HTTP | path | sso | set the app's base URL to `/<slug>`, or use cookie-root |

## Security model

Every service is reachable from the internet through Cloudflare → Traefik → Styx.
Read this section before exposing anything.

- Rate limiting and IP banning (`styx-ratelimit`, `ip-ban-gate`) apply to every service route.
- Identity headers (`X-Styx-*`, `X-authentik-*`) are stripped from client requests.
- **Bypass rules are the only unauthenticated surface** (see above), plus `app-native`
  services, where Styx does no authentication at all.
- **Verify upstream TLS off** means traffic between Styx and that host can be intercepted
  on your LAN. Use it only for self-signed appliances such as Unraid.
- The cookie-root routing cookie is a selector, not a credential: access is checked on
  every request.
- **Access checks are internal.** forwardAuth calls
  `/internal/services/<slug>/auth-check` (and `/internal/workstations/<id>/auth-check`, `/internal/instances/<id>/auth-check`), paths
  no Traefik router exposes. They authenticate only with the `styx_proxy` cookie.
- **Network isolation.** Proxied containers sit on `styx-services` with Traefik only, so
  they cannot reach the Styx API or the Docker socket proxy.
- **Client IPs** (rate limits, bans, audit) come from `CF-Connecting-IP` /
  `X-Forwarded-For` only when the socket peer is in `TRUSTED_PROXY_CIDRS` (default:
  loopback plus Docker's default bridge pools `172.16.0.0/12,192.168.0.0/16`; widen it if
  `daemon.json` sets other pools). `CF-Connecting-IP` is ignored when
  `DEPLOY_MODE=direct`.

### Cookie split

Proxied apps share the Styx origin, so Styx scopes its cookies to keep API tokens away
from them:

| Cookie | Path | Accepted by |
|---|---|---|
| `access_token` | `/api` | API only |
| `refresh_token` | `/api/auth` | refresh and logout only |
| `styx_proxy` | `/` | forwardAuth only; refused by the API |
| `csrf_token` | `/` | double-submit check (not a credential) |

`styx_proxy` is bound to the session's refresh-token family, so logout, refresh-reuse
detection, password change and admin reset or deactivation all invalidate it. Styx
strips its own cookies from every request it forwards to a proxied app, so upstreams
never see Styx credentials.

### Same-origin warning

JavaScript served by a proxied app runs on the Styx origin. It cannot read the HttpOnly
tokens, but it can make same-origin `fetch('/api/...')` calls that the browser sends with
the user's `/api` cookies, so it can act with the **viewing user's Styx rights**.
Treat every proxied app as trusted code. Admins should use a non-admin account for daily
app use. The service form requires you to acknowledge this. A full fix needs per-service
origins (subdomains), which is out of scope for now.
