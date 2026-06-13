# Outdated-agent detection + update command — design

Date: 2026-06-13
Status: approved (design)
Branch: `fix/logout-session-close-and-instance-502`

## Problem

Enrolled workstation agents run an installed copy of `styx_agent.py` (+ `engine.py`,
`gateway.py`, `selkies_launcher.py`) pulled once at enrollment. There is no
auto-update. When the agent changes (e.g. `0.4.1 → 0.4.2`, which added
`drop_clients` so logout actually drops the stream), already-enrolled boxes keep
running the old build and silently miss the new behavior. Admins have no way to
see which boxes are stale or how to update them.

## Goals

- Surface, per workstation, whether its agent is outdated vs the build the server
  currently serves.
- Give admins a copy-paste command to update a stale box.
- No remote code execution — the admin runs the command on the box (chosen for
  safety; a bad remote self-update could brick a headless agent with no rollback).

## Non-goals (YAGNI)

- Remote/one-click self-update.
- Bulk "update all".
- Updating the venv / wheelhouse / system packages. The update command refreshes
  only the agent `.py` files, which carry the behavior. Bigger upgrades (new
  wheels/artifacts) still go through full re-enrollment.

## Source of truth for "latest version"

The server already serves the current agent files from `AGENT_DIR`
(`./agent` mount; `GET /api/enroll/agent.py` → `styx_agent.py`). The latest
version is therefore whatever `AGENT_VERSION` is in that served file.

- New helper `get_latest_agent_version() -> str` in
  `backend/app/services/workstations.py`: read `AGENT_DIR/styx_agent.py`, regex
  `AGENT_VERSION = "X.Y.Z"`, return the string. Cache the parse (module-level,
  keyed by file mtime) so it is not re-read every request. Return `""` if the
  file is missing/unparseable (→ nothing is flagged outdated; fail safe).

## Backend changes

### Schema — `WorkstationOut` (`schemas.py`)

Add:

```python
agent_outdated: bool = False
```

`agent_outdated = bool(latest) and ws.agent_version not in ("", latest)`.
Empty version (pending / never-reported) is never flagged.

`_out(...)` in `routers/workstations.py` gains a `latest_version: str` parameter
(passed once by the caller so the parse happens per-request, not per-row) and
computes `agent_outdated`.

### Update-command endpoint

```
GET /api/workstations/{ws_id}/update-command   (admin only)
```

Returns:

```python
class WorkstationUpdateCommandOut(BaseModel):
    latest_version: str
    current_version: str
    lan_command: str | None     # None when no LAN URL configured/detected
    public_command: str
    lan_url_source: str         # env | detected | none
```

Command resolution mirrors `mint_enroll_token` (`lan_enroll_url()` +
`public_base = https://{DOMAIN}`). No enrollment token is needed — the
`/api/enroll/*.py` endpoints are public.

Command shape (one per base URL), built by a new
`build_update_command(base_url, *, ca_pin=None) -> str` helper next to
`build_enroll_command`:

```sh
INSTALL="$HOME/.local/share/styx-agent"
for f in agent.py:styx_agent.py engine.py:engine.py \
         gateway.py:gateway.py selkies_launcher.py:selkies_launcher.py; do
  curl -fsSL{k} "<base>/api/enroll/${f%%:*}" -o "$INSTALL/${f##*:}"
done
systemctl --user restart styx-agent
```

`-k` is added only for the LAN (self-signed) variant, matching how the enroll
command treats LAN TLS. Exact flag wiring follows the existing
`build_enroll_command` conventions.

## Frontend changes (`components/system/workstations-panel.tsx`)

- Next to the agent version, render an amber **"Outdated"** badge when
  `ws.agent_outdated` (reuse the existing `STATUS`/badge styling).
- On outdated rows, an **"Update"** button opens a small dialog showing the
  update command with a copy button — reuse the existing enroll-command copy
  pattern (`copy(...)` + the lan/public command blocks already in this panel).
- API client: `api.workstationUpdateCommand(id)` → `GET …/update-command`.

## Tests

Backend:
- `get_latest_agent_version()` parses the served file; returns `""` when missing.
- `agent_outdated` is `true` for an old version, `false` for the latest, `false`
  for empty/pending.
- `GET /{ws_id}/update-command` returns 200 with `latest_version`,
  `public_command` containing the enroll URLs + `systemctl … restart`, and
  404 for an unknown id; admin-gated (non-admin → 403).

Frontend: `tsc --noEmit` clean.

## Affected files

- `backend/app/services/workstations.py` — `get_latest_agent_version`,
  `build_update_command`
- `backend/app/schemas.py` — `WorkstationOut.agent_outdated`,
  `WorkstationUpdateCommandOut`
- `backend/app/routers/workstations.py` — pass latest into `_out`, new endpoint
- `backend/tests/test_workstation_admin_api.py` — endpoint + outdated tests
- `frontend/src/api/client.ts` — `workstationUpdateCommand`
- `frontend/src/components/system/workstations-panel.tsx` — badge + dialog
- `frontend/src/components/system/` — small update-command dialog (or inline)
