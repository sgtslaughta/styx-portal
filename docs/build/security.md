# Security model

Summary of the threat model and the controls in code. Operator-facing hardening
steps are in the Operate section.

## Threat model

| Threat | Control |
|--------|---------|
| Credential stuffing and brute force | Layered defense (below) |
| Stolen session cookie used against the API | Short access TTL, refresh rotation with reuse detection, `token_version` and `jti` revocation |
| Proxied app abusing Styx cookies | Path-scoped cookies, separate `styx_proxy` token the API refuses, cookie stripping on forwardAuth |
| CSRF | Double-submit token on all unsafe cookie-authenticated requests; same-origin guard for admin writes |
| Header spoofing (`X-Styx-User`, `Remote-User`, ...) | Traefik strips known names; backend refuses disguised variants |
| Malicious or compromised container escaping | Docker socket via proxy, no DinD, isolated networks, desktop image isolation (ADR 0005) |
| Compromised workstation agent | Per-workstation bearer token (stored hashed); can only call `/api/agent/*` for itself |
| Clickjacking / XSS | CSP, `X-Frame-Options: DENY`, `nosniff`, HSTS |
| Supply chain | SHA-pinned actions, pinned docs build, Trivy, bandit (ADR 0006) |

!!! warning "Out of scope"
    Styx assumes a trusted host. Anyone with the Docker socket, the database
    file or `JWT_SECRET` can impersonate any user.

## Authentication

* **Local login**: Argon2id password hashes (`security/passwords.py`), password policy from runtime settings.
* **JWTs** (`security/tokens.py`, HS256 with `JWT_SECRET`): access token carries `sub`, `role`, `type`, `tv` (user `token_version`) and `jti`. A mismatch on `tv` or a denylisted `jti` yields 401. Password change, role change or disable bumps `token_version`.
* **Refresh tokens** live in `refresh_tokens` as families; reusing a rotated token revokes the family. Sessions have an absolute cap (`SESSION_MAX_AGE`; `MATRIX_SESSION_MAX_HOURS` for card sessions).
* **First run**: `POST /api/auth/setup` requires a one-time code logged at boot and stored in `<data>/setup-token` (0600), deleted once an admin exists.
* **Forced password change**: `must_change_pw` restricts the user to `/auth/me`, `/auth/change-password`, `/auth/logout`.
* **Admin writes** must originate from the Styx SPA (`security/same_origin.py`).

### Matrix-card 2FA

A 5x10 grid of 3-character codes (`services/matrix_card.py`). Login asks for 3
random cells; verification is constant-time and fails closed. The card is stored
Fernet-sealed (`users.matrix_card`); a new card sits in `matrix_pending` until
activated. A short-lived `styx_mfa` cookie carries the challenge between steps,
and the device marker (`styx_device`) feeds per-device throttling.

### SSO (OIDC/OAuth2)

`authlib`; providers in `oauth_providers` with Fernet-encrypted client secrets;
identities in `federated_identities` (unique provider+subject). Provisioning is
**pre-authorized only**: the verified email must match an existing user or an
open invite. Identity details come from the userinfo endpoint (no id_token/JWKS
parsing). State and PKCE verifier travel in the `oauth_tx` cookie.

## Brute-force layers

| Layer | Where | Behaviour |
|-------|-------|-----------|
| L1 proxy rate limit | Traefik `styx-ratelimit` | Average and burst per IP (settings `TRAEFIK_RATELIMIT_*`) |
| L1b IP ban gate | Traefik forwardAuth `ip-ban-gate` -> `/api/auth/ban-check` | Banned IPs refused before reaching the app |
| L2 app rate limit | `middleware/rate_limit.py` | `RATE_LIMIT_AUTH` (default 5/60 on `/auth/*`), `RATE_LIMIT_DEFAULT`, instance-create limit |
| L3 per-user lockout | `abuse.LoginLockout` | `LOCKOUT_THRESHOLD` failures lock the account for `LOCKOUT_DURATION`; a global per-username throttle applies across IPs |
| L4 per-IP ban | `abuse.IpFailTracker` + `BannedIP` | `BAN_FAIL_THRESHOLD` failures in `BAN_FAIL_WINDOW` ban the IP for `BAN_DURATION` (IPv6 keyed by /64) |

Client IP is trusted from `CF-Connecting-IP` only when the peer is in
`TUNNEL_PEER_CIDRS` (or a proxy in `TRUSTED_PROXY_CIDRS`/own subnets), so a LAN
client cannot forge it.

## Secrets at rest

* `JWT_SECRET` (env or `SECRETS_FILE`): placeholder values are rejected at boot.
* `security/crypto.py`: Fernet key = HKDF-SHA256(JWT_SECRET, info `selkies-oauth-secret-enc`). Used for OAuth client secrets, matrix cards and each workstation's gateway password (`selkies_password_enc`).
* Enrollment tokens and agent tokens are stored as SHA-256 hashes; plaintext is shown once.

!!! danger "Rotating JWT_SECRET"
    Changing `JWT_SECRET` invalidates every session **and** makes all Fernet-sealed
    values (SSO secrets, matrix cards, workstation passwords) undecryptable.
    Re-enter SSO secrets, re-issue cards and re-enroll workstations after a
    rotation (the gateway password is generated at enrollment and there is no
    re-save path).

## Headers and CSP

`SecurityHeadersMiddleware` sets on every response: `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
a restrictive `Permissions-Policy`, HSTS (1 year, includeSubDomains) and a CSP of
`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'`.
Routes may set a scoped CSP first (`setdefault`), e.g. the SSO test page. Styx's
own notice pages use `SAMEORIGIN_HEADERS` to render inside the shell frame.
API docs (`/docs`, `/openapi.json`) are off unless `ENABLE_DOCS`.

## Agent token and gateway auth

* **Agent -> portal**: `Authorization: Bearer <agent_token>`; the backend hashes it and matches `workstations.agent_token_hash`. `/api/agent/*` and `/api/enroll/*` are CSRF-exempt because they carry no cookies.
* **Portal -> gateway**: the gateway requires HTTP Basic (user `styx`, a per-workstation random password). The backend keeps the password Fernet-encrypted and injects the `Authorization` header from the forwardAuth response, so portal users never see it. Direct LAN visits get a browser prompt.
* **Workstation addresses**: `WORKSTATION_ALLOW_CIDRS` restricts which `lan_ip` an agent may register (mandatory on k8s so an agent cannot aim Traefik at in-cluster services).
* **Cross-site sockets**: the gateway refuses cross-site WebSocket upgrades.
* The agent runs as the user (no root), never alters the user's real `~/.config`, and installs nothing from third-party apt sources.
