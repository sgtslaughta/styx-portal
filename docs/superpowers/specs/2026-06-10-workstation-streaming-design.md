# Physical Workstation Streaming ("Styx Agent") — Design

**Date:** 2026-06-10
**Status:** Approved
**Scope:** Enroll physical Linux workstations into Styx Portal and stream their desktops (video + audio) to browsers via Selkies, alongside existing container instances.

## Goals

- Admins enroll physical Linux workstations via a server-minted, copy-paste one-liner.
- Workstations stream full desktop video + audio to the browser using the same Selkies technology as the portal's containers.
- Support machines running X11 (capture the existing session) and pure Wayland (agent starts its own compositor session — Selkies cannot capture existing Wayland sessions; confirmed upstream limitation).
- GPU-accelerated encoding for gaming-class performance (NVENC / VAAPI, 60 fps default).
- Enrollment uses industry-standard join-token practice (single-use hashed token + TLS CA pinning, k3s/Teleport style).
- Agent removal is one command; troubleshooting is first-class (doctor command, clear preflight errors, health reporting).
- Enrollment and agent traffic use the server's **local LAN URL**, never the public (Cloudflare-tunneled) domain.

## Non-Goals (v1)

- Capturing an existing Wayland session (upstream Selkies issue #46 is open/unfunded).
- Reverse-tunnel connectivity for workstations outside the server's LAN (design leaves room; not built).
- Windows/macOS agents.
- Docker-based agent (decided against: native tarball install chosen).

## Key Research Facts

- Selkies 2.x (the stack inside `linuxserver/docker-baseimage-selkies`) captures existing X11 displays via pixelflux/ximagesrc; bare-metal install supported via portable tarball (glibc ≥ 2.17) or pip.
- `PIXELFLUX_WAYLAND` does **not** attach to a running mutter/kwin session — it starts a Smithay-based compositor. We reuse that behavior deliberately for Wayland machines.
- New Selkies transport is WebSocket-capable on a single data port; auth via HTTP basic auth or token. Traefik can proxy it exactly like container instances.
- pixelflux Wayland path supports zero-copy GPU encode (GBM → DmaBuf → VAAPI/NVENC).

## Architecture

```
Browser ──► Traefik ──► workstation LAN IP:PORT (Selkies, basic-auth)
                │
Portal backend ◄── heartbeat (HTTPS + Bearer agent token) ── styx-agent daemon (systemd --user)
                                                                └─ supervises Selkies process
```

- **X11 workstation:** Selkies attaches to existing `DISPLAY=:0` — true mirror of the physical desktop.
- **Wayland workstation:** agent launches its own Smithay compositor session (separate desktop on the workstation's hardware, not a mirror).
- **GPU:** preflight detects NVIDIA (→ `nvh264enc`) or Intel/AMD (→ VAAPI); falls back to CPU `x264enc` with an explicit warning. 60 fps default. Encoder/bitrate/fps adjustable per workstation in admin UI, synced via heartbeat.
- **Audio:** PulseAudio/PipeWire capture → Opus; microphone passthrough supported, same as containers.

## Data Model (new tables)

### `Workstation`

| Field | Notes |
|---|---|
| id | UUID PK |
| name | display name, admin-editable |
| subdomain | unique, indexed — used in Traefik host rule |
| hostname | reported by agent |
| lan_ip | reported + updated via heartbeat |
| port | Selkies port on workstation (default assigned at enrollment) |
| status | `pending` \| `online` \| `offline` \| `revoked` |
| display_server | `x11` \| `wayland` |
| gpu_info | JSON (vendor, model, encoder selected) |
| os_info | JSON (distro, kernel, glibc) |
| agent_version | semver string |
| agent_token_hash | SHA256 of long-lived bearer token |
| selkies_password_enc | Fernet-encrypted (existing HKDF(JWT_SECRET) key pattern) |
| stream_settings | JSON: encoder, fps, bitrate |
| all_users | bool — expose to every authenticated user |
| last_heartbeat | datetime |
| last_error | text reported by agent |
| created_by | FK users.id |
| created_at | datetime |

### `WorkstationEnrollmentToken`

Mirrors the proven `Invite` pattern: `token_hash` (unique, indexed), `expires_at` (24 h), `used_at`, `created_by`, `created_at`. Single-use.

### `WorkstationAccess`

Junction: `workstation_id` + `user_id` (unique pair). Admin-managed allow-list; `all_users` flag bypasses.

## Enrollment Flow

1. **Mint:** Admin clicks *Enroll workstation*. Server generates `secrets.token_urlsafe(32)`, stores SHA256 hash, returns one-liner (raw token shown once):

   ```
   curl -fsSL https://SERVER_LAN/api/enroll/script | bash -s -- \
     --token <TOKEN> --server https://SERVER_LAN --ca-pin sha256:<FP>
   ```

   - `SERVER_LAN_URL` is a new backend setting (env-driven). The minted command never references the public tunneled domain.
   - `--ca-pin` carries the SHA256 fingerprint of the server's TLS cert so the script can trust a self-signed LAN cert without `--insecure`.

2. **Preflight (script):** numbered checks, each failure prints exact remediation:
   1. Supported distro / glibc ≥ 2.17
   2. Display server detection (X11 → mirror mode; Wayland → own-compositor mode)
   3. GPU + encoder detection (`nvidia-smi`, `vainfo`); warn on CPU fallback
   4. User in `video`/`render` groups (needed for DRM zero-copy); remediation: `usermod` command
   5. Audio stack present (PipeWire or PulseAudio)
   6. Server reachable at LAN URL, cert matches pin
   7. Selkies port free
   8. systemd user session + linger capability

3. **Install (script):** downloads Selkies portable tarball **from the portal backend** (backend caches the release artifact — works on isolated LANs), installs to `~/.local/share/styx-agent/`, writes config to `~/.config/styx-agent/config.json`, installs systemd `--user` units (`styx-agent.service`), runs `loginctl enable-linger` (the only sudo action, prompted explicitly).

4. **Register:** agent POSTs hostname, IPs, display server, GPU, agent version with the enrollment token. Server validates hash + TTL + unused, consumes token, creates `Workstation`, mints:
   - long-lived **agent token** (returned raw once, SHA256 stored),
   - subdomain,
   - Selkies basic-auth password (Fernet-encrypted at rest),
   - initial stream settings.

5. **Heartbeat:** every 30 s, `POST /api/agent/heartbeat` with Bearer agent token. Payload: status, lan_ip, health (selkies process up, encoder active, last error). Response: desired state — updated stream settings, or `revoked` (agent stops Selkies, disables itself, prints uninstall hint). Missed heartbeats > 90 s ⇒ server marks `offline` (session-monitor loop extension).

## API Surface

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/workstations/enroll-tokens` | admin | mint enrollment token + one-liner |
| `GET /api/enroll/script` | none (static) | serves enrollment bash script |
| `GET /api/agent/artifacts/selkies.tar.gz` | none | cached Selkies tarball |
| `POST /api/enroll/register` | enrollment token | consume token, create Workstation |
| `POST /api/agent/heartbeat` | agent token | status/health up, desired state down |
| `POST /api/agent/deregister` | agent token | uninstall notification |
| `GET /api/workstations` | admin | list all |
| `PATCH /api/workstations/{id}` | admin | rename, stream settings, all_users |
| `PUT /api/workstations/{id}/access` | admin | set assigned user list |
| `DELETE /api/workstations/{id}` | admin | revoke + remove |
| `GET /api/workstations/mine` | user | assigned workstations for dashboard |

Agent endpoints are CSRF-exempt (token-authenticated, no cookies). All admin mutations audit-logged (`workstation.enroll`, `workstation.revoke`, `workstation.access_change`).

## Routing & Stream Access

- `route_writer.py` extended: for each `online` workstation, emit Traefik router `Host(ws-{subdomain}.{domain})` → service `https://{lan_ip}:{port}` with `serversTransport` (`insecureSkipVerify`) — identical machinery to container instances with `tls_skip_verify`.
- Stream gated by the same middleware chain instances use, plus per-workstation Selkies basic-auth credentials minted by the server.
- Dashboard shows assigned workstations as cards (online/offline badge); Connect behaves like a container instance.

## Removal

- **On workstation:** `styx-agent uninstall` — stops/disables units, removes `~/.local/share/styx-agent` + config, calls `deregister`. Single command, no root (linger removal optional, prompted).
- **From server:** admin *Remove* revokes the agent token and deletes routes. Agent learns `revoked` at next heartbeat, stops streaming, prints the uninstall command. Admin UI also displays the uninstall one-liner for manual cleanup of dead machines.

## Troubleshooting

- `styx-agent doctor`: checks service state, Selkies process, port listening, server reachability + cert pin, last heartbeat ack, active encoder. Prints pass/fail per check with remediation.
- `styx-agent status`: one-line summary.
- Logs: `~/.local/share/styx-agent/logs/` (agent + Selkies stdout/err, rotated).
- Heartbeat health payload surfaces in admin UI: status badge, last seen, last error. Admin Health page gains a Workstations section.
- Preflight failures use numbered error codes (`E01`–`E08`) matching docs.

## Frontend

- **Admin Settings → Workstations panel** (mirrors Users panel): table of workstations (status, GPU, IP, last seen), *Enroll* button → modal with one-liner + copy button + TTL countdown, per-row drawer: rename, user assignment (or all-users toggle), stream settings, remove (with uninstall instructions).
- **Dashboard:** workstation cards alongside instance cards.

## Security Summary

- Enrollment token: 32-byte urlsafe, SHA256 at rest, single-use, 24 h TTL, audited.
- Agent token: per-workstation bearer, SHA256 at rest, revocable, scoped to agent API only.
- Selkies basic-auth password: Fernet-encrypted at rest (existing key derivation from JWT_SECRET).
- TLS CA pinning embedded in the minted command; no `--insecure` anywhere.
- Agent endpoints rate-limited like auth endpoints; enrollment script served read-only.

## Agent Implementation Notes

- Agent daemon: single-file Python, **stdlib only** (urllib, json, subprocess) — no pip deps on the workstation beyond the Selkies tarball contents.
- Enrollment + uninstall scripts: bash, shellcheck-clean.
- Server caches the Selkies release tarball on first enrollment (configurable pinned version) and serves it to agents.

## Testing

- pytest (existing in-memory SQLite + mocked patterns): token mint/expiry/reuse/consume, register happy + failure paths, heartbeat state machine (online/offline/revoked), settings sync, route-writer workstation routes, access control (admin vs assigned user vs unassigned), audit entries.
- shellcheck CI step for `enroll.sh` / `uninstall.sh`.
- Agent daemon unit tests (mock server with `http.server`).

## Decisions Log

- Wayland: own-compositor takeover (user choice) — existing-session capture impossible upstream.
- Networking: direct LAN routing, Traefik → workstation IP (user choice).
- Access: admin-assigned users + all-users flag (user choice).
- Agent form: systemd `--user` service + native Selkies tarball (user choice; Docker agent rejected).
- GPU: mandatory goal — NVENC/VAAPI auto-selection, gaming defaults (60 fps).
