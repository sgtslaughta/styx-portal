# Agent remote update with auto-rollback — implementation plan

Branch `feat/agent-update` (worktree `/home/user/code/remote-access-update`). Agent version → **0.9.31**.
Goal: admins (or an auto setting) order an outdated workstation agent to update; it updates
itself on its next heartbeat; if the new agent is not healthy within 180 s it restores the old
files and reports `rolled_back`. No retry loop after a rollback.

## Contract (all three parts must match exactly)

### Workstation columns (backend `models.py` + `database.py` migrations list)
| column | type | meaning |
|---|---|---|
| `update_target` | TEXT, default "" | version ordered; "" = none |
| `update_state` | TEXT, default "" | "" / `requested` / `updating` / `ok` / `rolled_back` / `failed` |
| `update_error` | TEXT, nullable | ≤ 500 chars |
| `update_at` | TIMESTAMP, nullable | last state change |

### Admin API (`backend/app/routers/workstations.py`, `require_admin`, audit-logged)
- `POST /api/workstations/{id}/agent-update` → sets `update_target = get_latest_agent_version()`,
  `update_state="requested"`, `update_error=None`, `update_at=now`. 409 if latest is "" or
  agent already at latest. Returns the `WorkstationOut`.
- `POST /api/workstations/agent-update-outdated` → same for every workstation with
  `status=="online"` and outdated. Returns `{"requested": n}`. Register BEFORE `/{ws_id}` routes.
- `WorkstationOut` gains `update_state: str = ""`, `update_error: str | None = None`,
  `update_target: str = ""`.

### Setting (`backend/app/services/settings_store.py`, same `_spec` pattern as TURN ones)
`AGENT_AUTO_UPDATE`, group of the other workstation settings, bool, default False,
label "Auto-update workstation agents", help "Outdated agents update themselves on their next
check-in; a failed update rolls back and is not retried until an admin asks again."

### Agent-token API (`backend/app/routers/agent.py`)
- `GET /api/agent/update-manifest` (dep `get_agent_workstation`) →
  ```json
  {"version": "0.9.31",
   "files": [{"remote": "agent.py", "local": "styx_agent.py", "sha256": "…", "size": 1234}],
   "deps": {"selkies": "2.1.0", "pixelflux": "2.2.1", "pcmflux": "2.2.0"}}
  ```
  `files` = `AGENT_UPDATE_FILES` (+ `("uninstall", "uninstall.sh")`), hashed from the agent dir
  (reuse `_agent_dir()` logic from enroll.py — move it to `services/workstations.py` as
  `agent_dir()`). `deps` = regex `\b(selkies|pixelflux|pcmflux)==([\w.]+)` over the served
  `enroll.sh`. Put the helper `build_update_manifest()` in `services/workstations.py`.
- Heartbeat response gains `update: dict | None = None`:
  `{"version": ws.update_target}` when `ws.update_state == "requested"` and
  `ws.agent_version != ws.update_target`, else None.
- Heartbeat request `health.update` (dict from the agent, may be absent):
  `{"state": "updating|ok|rolled_back|failed", "from": "0.9.30", "to": "0.9.31", "error": str|None}`.
  Apply only when `to == ws.update_target`: copy state + error (truncate 500), `update_at=now`.
  Also: if `ws.update_target` and `ws.agent_version == ws.update_target` → `update_state="ok"`.
- Auto mode, in heartbeat: if setting `AGENT_AUTO_UPDATE` and latest != "" and
  `ws.agent_version not in ("", latest)` and NOT (`ws.update_target == latest` and
  `ws.update_state in ("requested","updating","rolled_back","failed")`) → request as above.

## Agent side (two new files; `styx_agent.py` is at 514 lines — add ≤ 6 lines there)

### `agent/agent_update.py` (imported by the agent)
- `STATE = INSTALL_DIR / "update-state.json"` (INSTALL_DIR = dir of this file).
- `report() -> dict | None`: contents of STATE or None. Agent puts it in `health_payload` as `"update"`.
- `on_heartbeat(cfg, hb)`: if `hb.get("update")` and `systemctl --user is-active --quiet
  styx-agent-update` is NOT active: copy `agent_updater.py` to
  `$XDG_RUNTIME_DIR/styx-agent-updater.py` and run
  `systemd-run --user --unit=styx-agent-update --collect /usr/bin/python3 <copy>
  --install-dir <INSTALL_DIR> --config <CONFIG_PATH> --target <version>`. Log one line.
- `confirm(version)`: called after a heartbeat returned 200 with selkies_ok and gateway_ok:
  if STATE says `state=="updating"` and `to == version` → rewrite with `state="ok"`.

### `agent/agent_updater.py` (standalone, stdlib only, runs in its own systemd unit)
1. Write STATE `{"state":"updating","from":<current AGENT_VERSION read by regex from
   styx_agent.py>,"to":target,"error":null,"at":ts}`.
2. `sys.path.insert(0, install_dir)`; `from portal_api import api, api_bytes` (reuses TLS pin).
   Load config JSON. `m = api(cfg, "/api/agent/update-manifest")`. Abort `failed` if
   `m["version"] != target`.
3. Deps check: for each dep, `glob(install_dir/venv/lib/python*/site-packages/<name>-<ver>.dist-info)`.
   Any missing → **full mode**, else **files mode**.
4. Files mode: download each file via `api_bytes(cfg, "/api/enroll/" + remote)` into
   `install_dir/.update-staging/`; verify sha256 + size; `py_compile.compile(..., doraise=True)` for
   `.py`. Any failure → write `failed` + error, delete staging, exit (nothing swapped).
   Backup current files to `install_dir/backups/<ts>-<from>/` (keep newest 3, delete older).
   `os.replace` each staged file into place. `systemctl --user restart styx-agent`.
5. Full mode: download `/api/enroll/script` to staging; run
   `bash <script> --upgrade --server <cfg["server"]>` (it backs up to `<install>.prev` and restarts
   the service itself). Non-zero exit → `failed`.
6. Health gate: poll STATE every 2 s up to 180 s for `state=="ok"`. On timeout:
   files mode → copy the backup files back + restart; full mode → run
   `<install>.prev/../styx-agent` swap via `health.rollback(install_dir)` logic (import it before
   step 5). Write `rolled_back` with error = "new agent not healthy in 180 s: " + last 15 lines of
   `journalctl --user -u styx-agent -n 15 --no-pager` (≤ 500 chars).
7. Every step writes STATE atomically (write tmp, `os.replace`).
- Testability: put each step in a small function; `main(argv)` wires them. Restart/journal/
  systemctl calls go through one `_run(cmd)` helper the tests monkeypatch. Timeout and poll
  interval are module constants the tests shrink.

### `styx_agent.py` wiring (≤ 6 lines)
`import agent_update`; `"update": agent_update.report()` in `health_payload`; after a successful
heartbeat: `agent_update.on_heartbeat(cfg, hb)` and, when `selkies_ok and gateway_ok`,
`agent_update.confirm(AGENT_VERSION)`. `AGENT_VERSION = "0.9.31"`.

### Distribution
Add `("agent_update.py","agent_update.py")` and `("agent_updater.py","agent_updater.py")` to
`AGENT_UPDATE_FILES` AND to the file loop in `agent/enroll.sh`.

## Frontend
- `api/client.ts`: types for the three new fields; `requestAgentUpdate(id)`,
  `requestAgentUpdateOutdated()`.
- Admin workstations panel / specs (where the outdated badge + update command already live):
  "Update agent" button (when `agent_outdated` and state not requested/updating), "Update all
  outdated" button in the panel header (when any outdated), state chip: requested → "Update
  queued", updating → "Updating…", ok → "Updated", rolled_back → "Rolled back" (error in title
  tooltip), failed → "Update failed". Keep the existing copy-paste one-liner as fallback.
- User workstation card: small "Agent out of date" badge when `agent_outdated` (no button).
- The AGENT_AUTO_UPDATE setting renders through the existing settings registry UI.

## Tests (gates: backend pytest + ruff, agent pytest, frontend `npm run build` + vitest)
- backend: request/409, update-outdated count, heartbeat sends update only while requested,
  health update applies only for matching target, ok clears via version match, rolled_back
  not re-requested in auto mode, manifest sha256/size/deps, admin-only + agent-token auth.
- agent: updater with monkeypatched `api`/`api_bytes`/`_run`: happy path swaps files + backup;
  bad sha → `failed`, files untouched; py_compile error → `failed`; gate timeout → files restored
  byte-identical + `rolled_back`; backups pruned to 3. `agent_update.confirm` + `on_heartbeat`
  skip when unit active.
- frontend: chip labels, buttons call the right endpoints.
