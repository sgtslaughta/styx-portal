# WebRTC + TURN from admin settings — plan

Goal: admins enter TURN credentials once in **Admin → Settings**; workstations set to
WebRTC stream through it. Proven live 2026-11-01: work PC (UDP P2P blocked) → Cloudflare
TURN (relay, udp) → GAME-01, HEVC hardware decode.

## Current state (verified)
- Selkies 2.1 flags: `--mode=webrtc`, `--enable-cloudflare-turn`, `--cloudflare-turn-token-id`,
  `--cloudflare-turn-api-token` (also generic `--turn-host/port/shared-secret/...`).
- Gateway passes `/api/webrtc/signaling/` through (branch `feat/webrtc-signaling`, uncommitted).
- System settings: `SettingsService` (`backend/app/services/settings_store.py`), types
  int/bool/rate only, values returned in plain text by `effective()`. No secret type.
- Secrets at rest: `encrypt_secret`/`decrypt_secret` (`backend/app/security/crypto.py`, Fernet from JWT_SECRET).
- Agent config: heartbeat returns `stream_settings` (`resolve_stream_settings`,
  `backend/app/services/ws_settings.py`); agent stores it in its config.json and
  `engine.build_selkies_cmd` turns it into flags.

## Steps

### 1. Backend: secret setting type (backend/app/services/settings_store.py)
- Add `type="secret"`: `_validate` accepts str ≤ 512 chars; `set` stores
  `encrypt_secret(value)`; `get` returns `decrypt_secret(...)`, or "" when unset.
- `effective()` returns `value: None, "is_set": bool` for secrets — never the plain text.
- Empty string on set = clear (same as reset).
- Tests: set → DB row is not plaintext; effective() hides the value; get() round-trips.

### 2. Backend: TURN specs (same file, new group `"webrtc"`, label "WebRTC / TURN")
- `WEBRTC_TURN_PROVIDER` — str enum `none|cloudflare` (default `none`).
- `CLOUDFLARE_TURN_TOKEN_ID` — secret.
- `CLOUDFLARE_TURN_API_TOKEN` — secret.
- Needs a small `enum` type (validate against `choices`); or reuse str + choices.

### 3. Backend: deliver to agents (ws_settings.py + routers/agent.py)
- `resolve_stream_settings`: when `ss.get("transport") == "webrtc"` and the provider is
  cloudflare with both secrets set, add `turn: {"provider": "cloudflare", "token_id": ..., "api_token": ...}`.
- Only to v0.9.29+ agents (version gate like `is_v2_agent`).
- Heartbeat is HTTPS + agent token: OK. Never log `stream_settings` with `turn` in it.

### 4. Agent: transport + TURN (agent/engine.py)
- `stream_settings.transport`: `websockets` (default) | `webrtc` → `--mode=`.
- `turn.provider == "cloudflare"` → `--enable-cloudflare-turn=true` + token args.
  argv rewritten in-process like the override (not visible in `ps`) — OR pass via env
  `SELKIES_CLOUDFLARE_TURN_TOKEN_ID` / `..._API_TOKEN` (preferred: env never hits argv).
- config.json already holds `selkies_password`: confirm it is mode 600.
- Tests: cmd/env for websockets, webrtc w/o TURN, webrtc + cloudflare; token never in cmd.

### 5. Agent: WebRTC idle + busy (agent/gateway.py / gateway_ws.py) — see Open questions
- Count a signaling WS as a live connection (state file `active_connections`) so
  occupancy + release work.
- Refuse a second controller signaling WS while one is live (same rule as `/api/websockets`).
- Idle: TBD.

### 6. Frontend
- Admin settings panel renders `secret`: password input, "Set"/"Not set" badge, Clear button.
- Workstation stream settings: **Transport** select (WebSockets / WebRTC), with a hint
  when WebRTC is chosen and no TURN is configured ("works on LAN / open networks only").

### 7. Ship
- Agent 0.9.29, backend/frontend minor bump; agent tests, backend pytest + ruff,
  `npm run build` + vitest.
- Live: set TURN in admin settings, GAME-01 transport=webrtc, delete GAME-01
  `stream-override.json`, repeat work-PC webrtc-internals check (relay/udp, H265).
- Rotate the Cloudflare TURN token used in testing (it was pasted in chat).

## Decisions (user, 2026-11-01)
1. **Both TURN providers**: `WEBRTC_TURN_PROVIDER` = `none|cloudflare|generic`.
   Generic = selkies `--turn-host/--turn-port/--turn-protocol/--turn-tls` +
   `--turn-shared-secret` (HMAC, coturn `use-auth-secret`) or `--turn-username/--turn-password`.
   Specs: `TURN_HOST` str, `TURN_PORT` int, `TURN_PROTOCOL` enum udp|tcp, `TURN_TLS` bool,
   `TURN_SHARED_SECRET` secret, `TURN_USERNAME` str, `TURN_PASSWORD` secret.
2. **Transport: both** — system default `WORKSTATION_TRANSPORT` (websockets|webrtc) +
   per-workstation `stream_settings.transport` override (`inherit` default).
3. **WebRTC idle (TURN bills per GB) — fail-safe beacon:**
   - Gateway already injects an idle watchdog into the selkies page. Extend it: the page
     posts `POST /styx/activity` (same-origin, Basic/forwardAuth) on real input
     (key/mouse/touch/gamepad), throttled to 1/15 s, only while the tab is visible.
   - Gateway tracks `last_input` per signaling session. No beacon for
     `idle_timeout_s` → close the signaling WS **and restart selkies** (kills the peer
     connection, so TURN traffic stops). Missing beacons = idle: a closed/hidden/crashed
     tab is cut too (fail-safe, no trust in the client).
   - Same warning banner + "I'm here" as WebSockets (lead `idle_warn_lead_s`).
   - Hard cap independent of input: `WEBRTC_MAX_SESSION_H` (default 8, 0 = off).
   - Busy: refuse a second controller signaling WS while one is live (4003 like WS).
4. **WebRTC refit (pointer/aspect):** resize `r,…` rides the data channel, so the
   gateway never refits the seat (seen 2026-11-01: game mode → browser 2560x1440,
   seat stayed 2560x1290 → pointer off). The injected page script also posts the
   client's size (`POST /styx/refit {w,h,dpr}`, same-origin, debounced 300 ms, on
   resize/fullscreen change); the gateway feeds it into the existing size-owner +
   `refit.request` path used for WebSockets. Swallow nothing (selkies still gets
   its own `r,`, harmless: "capture resized ... (requested ...)").
5. **TURN cost estimator** (Cloudflare: $0.05/GB egress from Cloudflare, first
   1,000 GB/month free, shared with SFU — pricing page 2026-09-22):
   - Settings: `TURN_FREE_GB_MONTH` int (1000), `TURN_USD_PER_GB` str/decimal ("0.05"),
     so price changes need no release.
   - Metering: per WebRTC session, bytes the client received over a **relay** pair
     (billable egress ≈ video+audio down; input up is tiny). Source, in order of trust:
     a) selkies server-side peer stats if exposed (selected pair type + bytesSent);
     b) else the page script adds `getStats()` relay `bytesReceived` to the activity
        beacon; gateway keeps per-session totals; agent heartbeat reports
        `turn_bytes` deltas; backend sums into a `turn_usage` table (month, workstation, user, bytes).
   - Admin → Settings → WebRTC/TURN card: month-to-date GB (per workstation/user),
     free allowance left, estimated $ = max(0, GB − free) × price, projected month-end
     (linear), plus a static what-if: "N h/month at B Mbps ≈ X GB ≈ $Y".
   - Optional phase 2: authoritative usage from Cloudflare GraphQL Analytics API
     (needs a separate read-only Account Analytics token) to reconcile the estimate.
6. Upstream issues (later, separate): `mode=auto` transport negotiation; hardware-decodable codec.
