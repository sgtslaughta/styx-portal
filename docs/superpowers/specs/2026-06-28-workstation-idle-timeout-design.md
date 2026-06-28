# Workstation Idle Timeout with Client Warning — Design

**Date:** 2026-06-28
**Status:** Approved (design), pending implementation plan
**Scope:** Workstation *seat* sessions (Selkies streaming agents). NOT docker instances.

## Problem

Operators perceive that remote workstation seats "never time out." In reality a
server-side idle disconnect already exists and is configurable, but two gaps make
it feel absent:

1. **Silent reconnect.** On idle the backend tells the agent to restart the
   gateway, dropping the websocket. A still-logged-in browser passes forward-auth
   and silently reconnects to the same desktop — so nothing visibly happens. The
   disconnect only "sticks" if the user has logged out of the portal.
2. **No warning.** The seat goes from active to dropped with no notice.

The goal: an idle timeout that is **visible** (a countdown warning the user can
cancel) and **effective** (the seat is actually released), reusing the existing
server-side machinery rather than replacing it.

## Existing machinery (reused, not rebuilt)

- `agent/gateway.py` tracks the last client→server input frame timestamp
  (`last_input_ts`) and live `active_connections`, mirrored to a state file.
- `agent/styx_agent.py::idle_seconds()` reports seconds-since-input each heartbeat.
- `backend/app/routers/agent.py` already disconnects an occupied seat once
  `idle_seconds >= idle_timeout` (per-workstation `stream_settings.idle_timeout_s`
  or system `WORKSTATION_IDLE_TIMEOUT_S`, default 900s). Uses an
  `idle_disconnect_sent` latch to avoid a per-heartbeat 502 restart loop when an
  idle browser auto-reconnects. Re-armed when `active_connections` returns to 0.
- When `active_connections` hits 0 the backend releases occupancy
  (`occupied_by/at = None`) and re-arms the latch. **This is the release path the
  client will trigger.**

## Decision

**Approach A — client-side warning, server-side backstop.** A gateway-injected
script in the Selkies stream page drives the user-facing countdown and closes the
stream sockets on expiry; the existing server-side timeout remains as an
independent backstop for closed/frozen tabs. Both read the same `idle_timeout_s`,
so they never disagree.

Rejected — **Approach B (server pushes warn/kill over a side channel):** more
authoritative but requires a new browser↔gateway protocol. Buys little, because
any activity already resets both the client clock and the server's `last_input_ts`
simultaneously (mouse/key on the stream page = a frame to Selkies = input the
server counts).

## Configuration

Three knobs. Admin-global via the runtime `settings_store` (auto-rendered in
Settings ▸ *timeouts*); per-workstation override via `Workstation.stream_settings`.

| Key | Default | Status |
|---|---|---|
| `idle_timeout_s` | 900 | **exists** (`WORKSTATION_IDLE_TIMEOUT_S`; per-ws `stream_settings.idle_timeout_s`) |
| `idle_warn_lead_s` | 60 | **new** — seconds before disconnect to show the overlay |
| `idle_timeout_enabled` | true | **new** — false ⇒ no client inject AND server skips (truly never times out) |

`idle_warn_lead_s` is clamped to `< idle_timeout_s / 2` at injection time so the
warning can't exceed the timeout.

## Components

### 1. Client watchdog (gateway-injected JS)

Injected into `index.html` before `</head>`, beside the existing `inject_title`,
via a new `gateway.py::inject_idle_watchdog(html, timeout_s, lead_s)`. When
`idle_timeout_enabled` is false or `timeout_s <= 0`, nothing is injected.

Behavior:

- Runs as an inline (non-module) script, so it executes during parse — **before**
  Selkies' deferred `type="module"` bundle. It wraps `window.WebSocket` to capture
  every socket Selkies subsequently opens (video / input-data / audio), keeping a
  reference list. This is the keystone: it lets us close exactly the sockets
  Selkies opened without depending on the vendored bundle's internals.
- Idle clock resets on `mousemove`, `mousedown`, `keydown`, `wheel`,
  `touchstart` (capture phase, passive). A 1s interval evaluates idle time.
- At `T − lead`: show a cancelable overlay — "Disconnecting in N s due to
  inactivity — move to stay" with an `aria-live` countdown. Any tracked input
  hides it and resets the clock.
- At `T`: close all captured sockets → `active_connections → 0` → the existing
  backend release path fires. Replace the view with a terminal overlay —
  "Session timed out due to inactivity" + a **Reconnect** button that reloads the
  page (a fresh session; the backend latch re-arms on `conns == 0`).

### 2. Server backstop (existing, lightly changed)

`routers/agent.py` idle disconnect is unchanged in logic but:

- gated by `idle_timeout_enabled` (skip entirely when false), and
- continues to use the same `idle_timeout_s`.

No timing offset versus the client: if the client closes first, `conns > 0` is
already false so the server condition is moot; if the tab is frozen/closed and the
client JS can't act, the server fires. They compose without coordination.

### 3. Config delivery to the gateway

The heartbeat response already carries per-workstation config to the agent. Add
the resolved idle fields (`idle_timeout_s`, `idle_warn_lead_s`,
`idle_timeout_enabled`) to it. `styx_agent.py` passes them to the gateway as
environment variables (`STYX_GW_IDLE_TIMEOUT_S`, `STYX_GW_IDLE_WARN_S`,
`STYX_GW_IDLE_ENABLED`) when launching it. The agent already relaunches the
gateway when `stream_settings` change, so config edits take effect on the next
heartbeat — no live reload needed.

## Data flow

```
admin/per-ws config ──heartbeat──▶ styx_agent ──env──▶ gateway ──inject──▶ stream page
                                       │                                        │
   activity (mouse/key) ──────────────┼── frame ──▶ selkies                     │
                                       │                                        │
   gateway last_input_ts ◀────────────┘                          client idle clock
        │                                                               │
   idle_seconds (heartbeat)                                   T-lead: overlay
        │                                                     T: close sockets ─┐
   backend backstop disconnect (if client didn't)                              │
        └────────────────── active_connections → 0 ◀──────────────────────────┘
                                       │
                          release occupancy + re-arm latch
```

## Files touched

- `backend/app/config.py` — `WORKSTATION_IDLE_WARN_LEAD_S = 60`,
  `WORKSTATION_IDLE_TIMEOUT_ENABLED = True`.
- `backend/app/services/settings_store.py` — two new specs (timeouts category).
- `backend/app/routers/agent.py` — carry idle config in heartbeat response; gate
  the existing disconnect on `idle_timeout_enabled`.
- `agent/styx_agent.py` — set `STYX_GW_IDLE_*` env on gateway launch; relaunch on
  idle-config change (reuse existing settings-change restart).
- `agent/gateway.py` — `inject_idle_watchdog()`; call it in the index handler.
- Frontend: none — settings auto-render from `settings_store`; the overlay is
  injected JS, not React.

## Testing

- `inject_idle_watchdog` (pytest, agent suite): script present with correct
  injected values; disabled / `timeout<=0` ⇒ no inject; `lead` clamped below
  `timeout/2`. This is the primary automated coverage — the injected JS is a
  Python string, so its *generation* is what pytest checks.
- WebSocket-wrap / countdown *behavior* runs in the browser, outside the Python
  suite. Verify via a focused `frontend` vitest test of the snippet (extract the
  watchdog body to a small JS module the gateway reads at startup, so it is both
  unit-testable and not a giant inline string), or a live smoke on a box. Decide
  module-vs-inline in the implementation plan; module is preferred for testability.
- `settings_store` exposes the two new keys with correct bounds (pytest).
- backend: disconnect skipped when `idle_timeout_enabled` is false (pytest).

## Edge cases

- `idle_timeout_enabled = false` or `idle_timeout_s = 0` ⇒ no inject, no server
  disconnect — never times out.
- Multiple Selkies sockets ⇒ wrap captures and closes all.
- Reconnect after timeout ⇒ fresh session; backend latch already re-arms on
  `conns == 0`.
- `idle_warn_lead_s >= idle_timeout_s` ⇒ clamped to `timeout/2` at injection.
- Activity definition is intentionally input-only (watching a stream without
  input counts as idle), matching the existing server-side semantics.

## Out of scope (follow-ups)

- **Docker instance idle is non-functional:** `Instance.last_activity` is never
  updated after start, so instance idle is measured from boot time. Separate bug,
  separate fix.
- Per-user (vs per-workstation) idle overrides.
- Lock-screen-on-idle as an alternative to disconnect.
