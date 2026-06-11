# Physical Workstation Streaming Guide

Styx Portal can stream physical Linux workstations to browsers alongside container instances. This guide covers enrollment, configuration, troubleshooting, and removal.

## Overview

**What it is:** Styx Agent is a lightweight Python daemon that runs on physical Linux machines and streams their desktop to browsers via the [Selkies 2.x](https://github.com/selkies-project/selkies) WebSocket streaming protocol. The native desktop (X11 session or a private virtual desktop) is encoded in real-time using GPU hardware (NVENC or VA-API) or CPU fallback, with audio support.

**Desktop modes (auto-detected at enrollment):**
- **Mirror mode:** Your existing X11 desktop is live-streamed. The remote user and you share control of the same session — input from the browser moves your local cursor. Requires a running X11 graphical session (`:0`, `:1`, etc.).
- **Second-seat mode:** A private GPU-accelerated desktop runs on the machine (via pixelflux's Smithay compositor + labwc window manager) alongside your login session. The physical screen is untouched. Your desktop, apps, and files are available to the remote user; no interference with local work. Used when the host is Wayland, headless, or when mirror mode is explicitly disabled.

**Architecture:**
- Enrollment script (`enroll.sh`) performs 8-step preflight, downloads agent daemon and prebuilt wheels from the portal, and registers the workstation.
- Agent daemon (`styx_agent.py`) runs as a systemd `--user` service, supervises the Selkies streaming engine (pixelflux + pcmflux), and sends heartbeats every 30 seconds.
- Traefik routes `/w/{subdomain}` traffic to the workstation's LAN IP on port 8443, where Selkies listens over WebSocket.
- Admin Workstations panel in **System → Workstations** controls access, stream settings, and enrollment status.

---

## Enrollment

### Quick Start

1. **In the Styx Portal UI:** Navigate to **System → Workstations** and click **Enroll workstation**.
2. **Copy the one-liner** from the enrollment token popup.
3. **On the workstation:** Log in to a graphical session and paste the command in a terminal.

The enrollment script will:
- Check for Python 3.10+, glibc ≥ 2.34, a graphical session or headless capability, and audio (PipeWire or PulseAudio).
- Auto-detect the capture mode: mirror (if X11 is found) or second-seat (if Wayland or headless). Can be overridden with `--mode mirror|seat`.
- Verify TLS fingerprint if `--ca-pin` is set.
- Install mode-specific dependencies (labwc + wl-clipboard for second-seat; VAAPI drivers for both).
- Download agent code, prebuilt wheels, and the Selkies app tarball from the server (all cached; ~150 MB total).
- Register the machine with the portal and save encrypted config.
- Start a systemd `--user` service that streams immediately.

**Token validity:** Tokens expire after 24 hours (configurable `ENROLL_TOKEN_TTL_HOURS`). If yours expires, mint a new one in the admin panel.

### Requirements

Before running enrollment on a workstation, ensure:

- **Distro:** Ubuntu 22.04+, Debian 12+, RHEL 9+, or equivalent (glibc ≥ 2.34). Check: `ldd --version`.
- **Network:** The machine can reach the portal's LAN address (`SERVER_LAN_URL`). This must be the portal's **local** IP or hostname (e.g., `https://192.168.1.10`), **not** a public tunnel.
- **Python 3.10+:** `python3` and `python3-venv` command available. Check: `python3 -V && python3 -m venv --help`.
- **Graphical environment:** X11 session (`:0`, `:1`, …) OR Wayland session OR headless with audio. For X11, `DISPLAY` and `XAUTHORITY` must be resolvable. Mirror mode requires an active X display.
- **Audio stack:** PipeWire or PulseAudio. Check: `pactl info` (should not error).
- **Port 8443:** Must be free; the Selkies listener binds to it.
- **systemd --user:** Required for service management. Standard in all graphical logins; fails only in `su` / `sudo` shells.
- **GPU drivers (optional, for hardware encoding):**
  - **NVIDIA:** `nvidia-smi` and `nvidia-smi -L` must work.
  - **AMD/Intel:** `vainfo` must work (VA-API).
  - Without GPU drivers, encoding falls back to CPU x264 (acceptable for low-bandwidth work).
  - **GPU group access:** On Wayland, be in the `render` group: `id -nG | grep -w render`. If not, `sudo usermod -aG render $USER && logout && login`.

---

## Server Setup

**Before first enrollment**, build and cache the agent artifacts on the server:

```bash
scripts/build_agent_artifacts.sh ./data/artifacts
```

This generates:
- `wheelhouse-x86_64.tar.gz` — Python wheels for pixelflux, pcmflux, selkies 2.x, and dependencies (covers Python 3.10–3.13).
- `selkies-web.tar.gz` — Browser UI dashboard.
- `libshim-x86_64.tar.gz` — Compatibility libraries (libva, libwayland) for older distros.

Rerun this after portal upgrades to sync agent versions.

## Configuration

All settings are environment variables or `.env` file entries on the **server**. Adjust them before enrolling workstations:

| Variable | Default | Purpose |
|---|---|---|
| `SERVER_LAN_URL` | `""` (auto-detects) | Local LAN address for enrollment commands. Example: `https://192.168.1.10` or `https://portal.local`. Workstations must reach this address. When unset, the portal auto-detects (usually correct; set explicitly in Docker bridge networks). |
| `SERVER_CA_PIN` | `""` (auto-pin) | Override for the TLS pin in enrollment commands. Format: `sha256:<hex>`. Leave empty: the portal auto-generates a self-signed LAN cert and pins it automatically. |
| `ARTIFACT_CACHE_DIR` | `/app/data/artifacts` | Server-side directory for cached agent wheelhouse, Selkies app tarball, and lib shims. Must be writable. Enrollment artifacts are served from here. |
| `AGENT_DIR` | `/app/agent` | Server path to the `agent/` directory (scripts and daemon). Mounted from the repo in Docker Compose. |
| `ENROLL_TOKEN_TTL_HOURS` | `24` | Lifetime of enrollment tokens (hours). Tokens are single-use and expire after this duration. |
| `WORKSTATION_OFFLINE_AFTER_S` | `90` | Heartbeat timeout (seconds). If a workstation doesn't heartbeat for 90+ seconds, it is marked offline. |
| `WORKSTATION_DEFAULT_PORT` | `8443` | Default Selkies port on workstations. Enrollment uses this; if busy, enrollment fails (E07). |
| `WORKSTATION_HEARTBEAT_S` | `30` | Agent heartbeat interval (seconds). Heartbeat reports status, config changes, and health. |

---

## Error Codes and Remediation

Enrollment runs 8 preflight checks. If any fail, the script prints an error code (E00–E08). Resolve each as follows:

| Code | Message | Remediation |
|---|---|---|
| E00 | `--token and --server are required.` | Run the one-liner from the admin Workstations panel. If copying manually, ensure both `--token <TOKEN>` and `--server <URL>` are present. |
| E01 | `Distro too old / python3 not found / glibc < 2.34` | Install Python 3.10+: `sudo apt install python3 python3-venv`. Update OS if glibc < 2.34 (need Ubuntu 22.04+, Debian 12+, RHEL 9+). |
| E02 | `Mirror mode requested but no X display found.` | Mirror mode requires an active X11 display. Either log into an X11 session, or use `--mode seat` for a private virtual desktop. Check X displays: `ls /tmp/.X11-unix/`. |
| E03 | `Dependency install failed (labwc, GPU drivers, etc).` | For seat mode, install manually: `sudo apt install labwc wl-clipboard` (Debian/Ubuntu). For GPU: `sudo apt install mesa-va-drivers` (AMD/Intel) or NVIDIA driver package. Restart agent afterward: `systemctl --user restart styx-agent`. |
| E04 | `Audio stack not found (PipeWire/PulseAudio).` | Install one: `sudo apt install pipewire` (Debian/Ubuntu) or `sudo dnf install pipewire` (Fedora). Verify: `pactl info` should succeed. |
| E05 | `Cannot reach server. Artifact download failed.` | Check: 1) Is `SERVER_LAN_URL` the **local LAN address**, not a tunnel? 2) Can the workstation reach it: `curl -kv https://<SERVER_LAN_URL>/api/health`? 3) On the server, did you run `scripts/build_agent_artifacts.sh ./data/artifacts`? |
| E06 | `TLS certificate fingerprint mismatch.` | The server's cert doesn't match the pinned `--ca-pin`. Causes: cert rotated (mint a new token), MITM (unlikely on LAN), or wrong host. Verify: `openssl s_client -connect <HOST>:443 2>/dev/null \| openssl x509 -fingerprint -sha256 -noout`. |
| E07 | `Port 8443 already in use.` | Find and kill the occupant: `sudo lsof -i :8443` or `sudo ss -ltnp \| grep :8443`. Or on the server, change `WORKSTATION_DEFAULT_PORT` to an unused port and re-enroll. |
| E08 | `systemd --user session unavailable.` | You are in a `su` or `sudo` shell. Log in as the user normally (SSH or `su - <user>`), then re-run enrollment. |

---

## Usage

### Connecting to a Workstation

1. **In the Styx Portal dashboard,** the **Workstations** section shows cards for each machine you have access to.
2. **When online:** The card shows a green "Online" badge and a **Connect** button. Click to open the stream in a new browser tab.
3. **Stream quality:** The agent sends the desktop at the configured framerate (default 60 fps) and bitrate (default 16 Mbps). Adjust in the admin Workstations panel.

### Checking Workstation Status

**From the agent on the workstation:**

```bash
# Show last heartbeat result (age, success/failure)
python3 ~/.local/share/styx-agent/styx_agent.py status

# Run diagnostics (checks service, port, cert, connectivity, encoder)
python3 ~/.local/share/styx-agent/styx_agent.py doctor

# View logs (Selkies output)
tail -f ~/.local/share/styx-agent/logs/selkies.log
```

**From the admin panel:** **System → Workstations** shows:
- **Status badge** (online / offline / pending / revoked)
- **Last heartbeat** timestamp
- **Last error** (if any)
- Auto-refreshes every 15 seconds

### Changing Stream Settings

**Admin panel:**
1. Click a workstation card.
2. Edit **framerate**, **bitrate_kbps**, or **encoder** in the JSON config.
3. The agent picks up the change on the next heartbeat (~30 seconds) and restarts Selkies.

**Encoder options:**
- `auto` (default): Selkies auto-detects (NVIDIA → nvh264enc, VAAPI → vah264enc, else x264enc).
- `nvh264enc` (NVIDIA)
- `vah264enc` (VAAPI/AMD/Intel)
- `x264enc` (software, CPU intensive)

---

## Troubleshooting

### Workstation Shows Offline

**Symptom:** Status badge says "Offline" even though the machine is powered on.

**Causes & fixes:**
1. **Service not running:**
   ```bash
   systemctl --user status styx-agent
   ```
   If stopped: `systemctl --user restart styx-agent`.

2. **Heartbeat timeout (>90s):** The agent hasn't called home. Run diagnostics:
   ```bash
   ~/.local/share/styx-agent/venv/bin/python ~/.local/share/styx-agent/styx_agent.py doctor
   ```
   This checks service, port, cert, connectivity, and encoder. Common issues: network unreachable, cert mismatch, engine crash.

3. **Network unreachable:**
   ```bash
   curl -kv https://<SERVER_LAN_URL>/api/health
   ```

### Stream is Black or Laggy

**Symptoms:** Window opens but shows black screen, or video is choppy/delayed.

**Causes & fixes:**
1. **No GPU encoder:** If `doctor` reports `encoder: x264enc` and you have a GPU:
   - **NVIDIA:** `sudo apt install nvidia-driver-*` + reboot.
   - **AMD/Intel:** `sudo apt install mesa-va-drivers` then check `vainfo`.
   - Restart: `systemctl --user restart styx-agent`.

2. **Mirror mode X display issue:** For mirror mode, check the X display is accessible:
   ```bash
   echo $DISPLAY  # Should be :0 or similar
   XAUTHORITY=~/.Xauthority xauth list | grep $DISPLAY
   ```
   If empty, the agent cannot access the display. Run doctor to diagnose.

3. **Engine logs:** Check for errors:
   ```bash
   tail -50 ~/.local/share/styx-agent/logs/selkies.log
   tail -50 ~/.local/share/styx-agent/logs/gateway.log
   ```

4. **Network/bitrate:** Reduce bitrate in admin panel (e.g., 16000 → 8000 kbps) if latency is high.

### "Revoked by server" Message

**Symptom:** Agent logs "Revoked by server. Stopping. To remove this agent run: `python3 ~/.local/share/styx-agent/styx_agent.py uninstall`".

**Cause:** An admin clicked **Revoke** on the workstation in the admin panel. This tells the agent to stop streaming gracefully and show uninstall instructions.

**Action:** Run the uninstall command if you no longer need the workstation, or contact the admin to re-enable it.

---

## Removal

### From the Workstation

On the machine, run:

```bash
python3 ~/.local/share/styx-agent/styx_agent.py uninstall
```

This stops the service, removes the agent and Selkies, and cleans up config/logs.

Alternatively, use the standalone uninstall script:

```bash
bash ~/.local/share/styx-agent/uninstall.sh
```

### From the Admin Panel

**Revoke (soft):**
1. **System → Workstations** → select the machine.
2. Click **Revoke**.
3. The agent receives the revocation on the next heartbeat, stops streaming, and shows the uninstall command to the operator.

**Purge (hard):**
1. **System → Workstations** → select the machine.
2. Click **Delete** (trash icon) to purge it from the database.
3. The workstation is immediately unreachable and removed from all users' access lists.
4. **Note:** The agent on the machine must still be uninstalled manually (or will fail to deregister and leave files behind).

**Typical flow:**
1. Click **Revoke** → agent stops cleanly within 30 seconds.
2. Admin runs uninstall on the workstation machine (or user self-serves).
3. Click **Purge** in the admin panel to remove it from the database.

---

## Advanced

### Capture Mode Overrides

By default, `enroll.sh` auto-detects the capture mode:
- **X11 session running** → mirror mode (live desktop capture).
- **Wayland session or headless** → second-seat mode (private virtual desktop).

To override:
```bash
# Force mirror mode on an X display
curl ... | bash -s -- --token ... --server ... --mode mirror --display :0

# Force second-seat mode (private virtual desktop)
curl ... | bash -s -- --token ... --server ... --mode seat
```

For X11 workstations where you prefer a private session, use `--mode seat`. The physical screen remains untouched, and the remote user gets a fresh desktop with access to the machine's apps and files.

### Hardware Encoder Selection

The agent auto-probes in order: NVENC (NVIDIA) → VA-API (AMD/Intel) → x264 (CPU). To force a specific encoder, edit the workstation config in the admin panel under `stream_settings.encoder`. Options: `nvh264enc`, `vah264enc`, `x264enc`, or `auto` (default).

### TLS

**Automatic (default):** When the LAN address has no publicly-valid certificate
(any host in tunnel mode, IP addresses in direct mode), the backend generates a
persistent self-signed certificate for it (`lan-certs` volume), Traefik serves
it on port 443, and the minted LAN command pins it two ways automatically:
`curl --pinnedpubkey 'sha256//…'` so the very first fetch of the enrollment
script verifies the self-signed server cryptographically, and `--ca-pin
sha256:…` so the script re-verifies and saves the cert the agent trusts.
Nothing to configure. The cert (and pins) only change if you change the LAN
address. (`-k` appears on the bootstrap line — it only skips CA-chain
validation of the self-signed root; identity is still enforced by the pinned
public key, so MITM fails closed.)

**Tunnel mode prerequisite:** publish ports 80/443 on the `traefik` service —
uncomment the `ports:` block in `docker-compose.yml`, then
`docker compose up -d traefik`.

**Manual override:** to pin your own certificate instead, set `SERVER_CA_PIN`:

```bash
echo | openssl s_client -connect <HOST>:443 2>/dev/null \
  | openssl x509 -fingerprint -sha256 -noout
# Outputs: sha256=AB:CD:...  → format as sha256:ABCD... (remove colons)
```

---

## Logs and Diagnostics

**Agent state file:**
```
~/.local/share/styx-agent/state.json
```
Last heartbeat timestamp, status (ok/failed), and error message.

**Engine logs:**
```
~/.local/share/styx-agent/logs/selkies.log   # Video/audio capture and stream
~/.local/share/styx-agent/logs/gateway.log   # HTTP gateway (auth, credential injection)
~/.local/share/styx-agent/logs/seat.log      # Second-seat mode logs (compositor, labwc)
```

**systemd user service logs:**
```bash
journalctl --user -u styx-agent -n 50
```
Agent daemon startup, crashes, restarts.

---

## Security Model

- **Token-based enrollment:** Enrollment tokens are single-use and expire after 24 hours (configurable). Each token mints a unique agent token at registration.
- **Per-workstation bearer token:** The agent authenticates to the portal with a unique token (stored hashed in the database). Compromising one workstation's token does not affect others.
- **TLS pinning (automatic):** The enrollment command pins the portal's LAN certificate fingerprint (auto-generated self-signed cert, or `SERVER_CA_PIN` override). Enrollment and all agent traffic verify against the pinned cert — MITM on the LAN fails closed, and no insecure connections are ever made.
- **Per-user access control:** Admins can restrict which users can connect to each workstation in the admin panel.
- **Stream access (forwardAuth):** Requests to `/w/<subdomain>/` are gated by Traefik forwardAuth against the portal — you must be logged in to the portal in the same browser, and your account must have access to that workstation. A 401 on the stream URL means you are not logged in; a 403 means your account is not assigned to that workstation.
- **Selkies credentials never reach the browser:** Each workstation's Selkies instance is protected by HTTP basic auth (random password, encrypted at rest). Traefik injects the `Authorization` header server-side after forwardAuth passes, so the password never appears in URLs, browser history, or logs. Direct LAN access to the workstation's Selkies port still requires that password.
- **Heartbeat revocation:** Admins can revoke a workstation at any time; the agent sees it on the next heartbeat (~30 s) and stops.

---

## Limits and Caveats

- **No SSH tunneling:** Workstations must have direct LAN connectivity to `SERVER_LAN_URL`. Remote access requires a VPN or SSH tunnel set up outside the portal.
- **Single stream per machine:** The agent streams one desktop per machine. For multi-monitor setups, use a virtual compositor or extended desktop.
- **Wayland mirror not supported:** The agent cannot mirror an existing Wayland desktop (upstream Selkies limitation; see [selkies#46](https://github.com/selkies-project/selkies/issues/46)). Wayland machines get a private second-seat desktop instead.
- **Display-only streaming:** Selkies streams the visual desktop; no file transfer or additional terminal. Use file sharing (NFS, Samba, sshfs) or SSH for files.
- **Performance:** Quality depends on network bandwidth, encoder choice, and GPU availability. Start with default settings and reduce bitrate/framerate on slow links.

---

## Support

For enrollment or streaming issues:
1. Run diagnostics: `~/.local/share/styx-agent/venv/bin/python ~/.local/share/styx-agent/styx_agent.py doctor`
2. Check logs: `tail -50 ~/.local/share/styx-agent/logs/{selkies,gateway,seat}.log`
3. Review the admin panel: click the workstation card to see "Last error".
4. Check the error codes above (E00–E08).
5. Consult server logs for registration/heartbeat failures.

For Selkies 2.x or pixelflux issues, see the [Selkies GitHub repository](https://github.com/selkies-project/selkies).
