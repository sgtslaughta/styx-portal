# Physical Workstation Streaming Guide

Styx Portal can stream physical Linux workstations to browsers alongside container instances. This guide covers enrollment, configuration, troubleshooting, and removal.

## Overview

**What it is:** Styx Agent is a lightweight Python daemon that runs on physical Linux machines and streams their desktop via [Selkies](https://github.com/selkies-project/selkies-gstreamer) — a WebRTC+GStreamer streaming stack that encodes desktop video/audio and sends it to the browser.

**Desktop modes:**
- **X11:** The agent mirrors your existing running X11 desktop (`:0`). Whatever you see locally is streamed.
- **Wayland:** Selkies cannot capture an existing Wayland session (upstream limitation; see [selkies-gstreamer#46](https://github.com/selkies-project/selkies-gstreamer/issues/46)). Instead, the agent starts its own separate desktop session (via Pixelflux compositor) on that machine. This session runs independently of your interactive login.

**Architecture:**
- Enrollment script (`enroll.sh`) performs 8-step preflight, fetches the agent daemon and Selkies tarball from the server, and registers the workstation.
- Agent daemon (`styx_agent.py`) runs as a systemd `--user` service, supervises Selkies, and sends heartbeats every 30 seconds.
- Traefik routes `/w/{subdomain}` traffic to the workstation's LAN IP on port 8443, where Selkies listens.
- Admin Workstations panel in **System → Workstations** controls access, streams settings, and enrollment status.

---

## Enrollment

### Quick Start

1. **In the Styx Portal UI:** Navigate to **System → Workstations** and click **Enroll workstation**.
2. **Copy the one-liner** from the enrollment token popup.
3. **On the workstation:** Log in to a graphical session and paste the command in a terminal.

The enrollment script will:
- Check for Python 3, glibc ≥ 2.17, a graphical session (X11 or Wayland), and audio (PipeWire or PulseAudio).
- Verify TLS fingerprint if `--ca-pin` is set.
- Download Selkies (cached on the server; ~200 MB).
- Register the machine with the portal.
- Start a systemd `--user` service that streams immediately.

**Token validity:** Tokens expire after 24 hours (configurable `ENROLL_TOKEN_TTL_HOURS`). If yours expires, mint a new one in the admin panel.

### Requirements

Before running enrollment on a workstation, ensure:

- **Network:** The machine can reach the portal's LAN address (`SERVER_LAN_URL`). This must be the portal's **local** IP or hostname (e.g., `https://192.168.1.10`), **not** a public tunnel.
- **Python 3:** `python3` command available.
- **glibc ≥ 2.17:** Selkies portable build requires it. Check with `ldd --version`.
- **Graphical session:** X11 (`:0` is standard) or Wayland. SSH sessions and headless machines are not supported.
- **Audio stack:** PipeWire or PulseAudio (usually bundled with desktop environments).
- **Port 8443:** Must be free; the Selkies listener binds to it.
- **systemd --user:** Required for service management. Standard in all user sessions; fails only in `su` / `sudo` shells.
- **GPU drivers (optional):** For hardware encoding:
  - **NVIDIA:** `nvidia-smi` + `nvidia-smi -L` must work.
  - **AMD/Intel:** `vainfo` must work (VAAPI).
  - Without GPU drivers, encoding falls back to CPU x264 (higher latency; suitable for low-framerate work).
- **Wayland group membership (Wayland only):** The user must be in `video` and `render` groups for hardware GPU access on Wayland:
  ```bash
  sudo usermod -aG video render $USER
  # Then log out and back in for the group to take effect
  ```

---

## Configuration

All settings are environment variables or `.env` file entries on the **server**. Adjust them before launching workstations:

| Variable | Default | Purpose |
|---|---|---|
| `SERVER_LAN_URL` | `""` (auto-detects the server's local IP) | Local LAN address used in the enrollment one-liner. Example: `https://192.168.1.10` or `https://portal.local`. Workstations must reach this address. When unset, the portal auto-detects its local IP (`http://<ip>` in tunnel mode, `https://<ip>` in direct mode) — inside a bridge-network container this detects the container IP, which is usually wrong, so set this explicitly in Docker deployments. The enroll dialog always also shows a public-URL command (`https://{DOMAIN}`) for machines outside the LAN; note streaming still requires the server to reach the workstation's IP. |
| `SERVER_CA_PIN` | `""` (auto-pin) | Override for the TLS pin in the enrollment command. Format: `sha256:<hex>`. Leave empty: the backend auto-generates a self-signed LAN cert and pins it automatically (see TLS Pinning below). |
| `SELKIES_TARBALL_URL` | `https://github.com/selkies-project/selkies-gstreamer/releases/download/v1.6.2/selkies-gstreamer-portable-v1.6.2_amd64.tar.gz` | Public URL to the Selkies portable tarball. The server downloads and caches it; workstations fetch from the server, not directly from GitHub. |
| `ARTIFACT_CACHE_DIR` | `/app/data/artifacts` | Server-side cache directory for the Selkies tarball. Pre-place `selkies.tar.gz` here for air-gapped deployments. |
| `AGENT_DIR` | `/app/agent` | Server path to the `agent/` directory (scripts and daemon). Mounted from the repo in Docker Compose. |
| `ENROLL_TOKEN_TTL_HOURS` | `24` | Lifetime of enrollment tokens (hours). Tokens are single-use and expire after this duration. |
| `WORKSTATION_OFFLINE_AFTER_S` | `90` | Heartbeat timeout (seconds). If a workstation doesn't heartbeat for 90+ seconds, it is marked offline and routes are refreshed. |
| `WORKSTATION_DEFAULT_PORT` | `8443` | Default Selkies port on workstations. Enrollment tries to use this; if busy, enrollment fails (E07). |
| `WORKSTATION_HEARTBEAT_S` | `30` | Agent heartbeat interval (seconds). The agent sends a heartbeat to the server every 30 seconds to report status. |

### Air-Gapped Deployments

If workstations cannot reach the internet:

1. **Download the Selkies tarball** from the configured `SELKIES_TARBALL_URL` on a machine with internet access.
2. **Place it** at `{ARTIFACT_CACHE_DIR}/selkies.tar.gz` on the portal server (e.g., `/app/data/artifacts/selkies.tar.gz` in the container, or `./data/artifacts/selkies.tar.gz` locally).
3. **Enrollment will use the cached file** instead of downloading.

---

## Error Codes and Remediation

Enrollment runs 8 preflight checks. If any fail, the script prints an error code (E00–E08) with a message. Resolve each as follows:

| Code | Message | Remediation |
|---|---|---|
| E00 | `--token and --server are required.` | Run the command from the admin Workstations panel; the token and server are prepended. If copying the one-liner manually, ensure both `--token <TOKEN>` and `--server <URL>` are present. |
| E01 | `python3 not found. Install it (apt install python3 / dnf install python3).` | Install Python 3: `sudo apt install python3` (Debian/Ubuntu) or `sudo dnf install python3` (Fedora/RHEL). Also: `glibc >= 2.17 required (found X.Y). Selkies portable build will not run.` — Update your OS or compile glibc locally (rare). Most distributions from 2015+ have glibc 2.17+. |
| E02 | `No display session found. Log into a graphical session first (or check loginctl show-session).` | You are in a headless/SSH environment. Log into the machine via the graphical login screen (GDM, LightDM, SDDM, etc.) or start an X server / Wayland session locally. Check: `echo $DISPLAY` (X11) or `echo $XDG_SESSION_TYPE` (Wayland). |
| E03 | `(Warning only)` Warning about missing GPU encoder or video/render group membership on Wayland. | To enable hardware encoding, install GPU drivers: **NVIDIA:** `nvidia-driver-*` package + verify `nvidia-smi -L` works. **AMD/Intel:** `libva` + `vainfo` must work. **Wayland users:** Run `sudo usermod -aG video render $USER` and log out/in. Without GPU drivers, encoding defaults to CPU x264 (acceptable for low-bandwidth work). |
| E04 | `Neither PipeWire nor PulseAudio found. Install one (apt install pipewire) for audio streaming.` | Install PipeWire or PulseAudio: `sudo apt install pipewire` (Debian/Ubuntu) or `sudo dnf install pipewire` (Fedora). Verify: `pactl info` (should print audio daemon info, not error). |
| E05 | `Cannot reach $SERVER from this machine. Check LAN routing/firewall (this must be the portal's LOCAL address, not the public tunnel).` | The workstation cannot reach `SERVER_LAN_URL`. Check: 1) Is `SERVER_LAN_URL` set to the **local LAN address**, not a public tunnel? 2) Is the portal listening on that address? 3) Is there a firewall blocking port 443 (HTTPS)? Try: `curl -kv https://<SERVER_LAN_URL>/api/health` from the workstation. Also appears for "Selkies download failed" or "Registration rejected" — check the server logs. |
| E06 | `TLS certificate fingerprint mismatch (expected ..., got ...). Wrong server or MITM.` | The server's TLS certificate does not match the pinned `--ca-pin`. Causes: 1) The cert changed (cert renewal/rotation); mint a new token with the new pin. 2) MITM attack (unlikely on LAN); verify the cert fingerprint manually: `openssl s_client -connect <HOST>:<PORT> 2>/dev/null \| openssl x509 -fingerprint -sha256 -noout`. 3) Wrong host/IP in `--ca-pin` — re-check the enrollment command. |
| E07 | `Port 8443 already in use. Free it or change WORKSTATION_DEFAULT_PORT on the server.` | Another service is listening on port 8443. Find and kill it: `sudo lsof -i :8443` or `sudo ss -ltnp \| grep :8443`. Or on the server, change `WORKSTATION_DEFAULT_PORT` to an unused port and re-enroll. |
| E08 | `systemd --user session unavailable. Log in as this user via a normal session (not su/sudo).` | You are running enrollment in a `su` or `sudo` shell, which doesn't start a systemd user session. Log in as the target user normally (via SSH to the machine, or `su - <user>` instead of `su <user>`), then re-run enrollment. |

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

**Symptom:** Status badge says "Offline" even though the machine is powered on and you logged in.

**Causes & fixes:**
1. **Service not running:** On the workstation, check:
   ```bash
   systemctl --user status styx-agent
   ```
   If stopped: `systemctl --user restart styx-agent`.

2. **Stale heartbeat (> 90 seconds):** The agent hasn't sent a heartbeat in 90+ seconds (default `WORKSTATION_OFFLINE_AFTER_S`). Check:
   ```bash
   python3 ~/.local/share/styx-agent/styx_agent.py status
   ```
   If it fails, run:
   ```bash
   python3 ~/.local/share/styx-agent/styx_agent.py doctor
   ```
   to diagnose. Common issues: network unreachable, cert mismatch, Selkies crashed.

3. **Network:** Verify the workstation can reach the portal:
   ```bash
   curl -kv https://<SERVER_LAN_URL>/api/health
   ```

### Stream is Black or Laggy

**Symptoms:** Window opens but shows black screen, or video is very choppy / delayed.

**Causes & fixes:**
1. **Encoder fallback (no GPU):** If `doctor` reports `encoder: x264enc` and your machine has a GPU, install drivers:
   - **NVIDIA:** `sudo apt install nvidia-driver-*` + reboot + verify `nvidia-smi -L` works.
   - **AMD/Intel:** Install `libva` + verify `vainfo` works.
   - Then restart the agent: `systemctl --user restart styx-agent`.

2. **X11 / Wayland not detected:** The agent may not be attached to the correct display. On X11:
   ```bash
   echo $DISPLAY  # Should be :0 or similar
   ```
   On Wayland, the agent starts its own session; no display needed.

3. **Selkies crashed:** Check logs:
   ```bash
   tail -50 ~/.local/share/styx-agent/logs/selkies.log
   ```
   Look for errors like permission denied, missing dependencies, or encoder issues. Restart:
   ```bash
   systemctl --user restart styx-agent
   ```

4. **High bitrate on slow network:** If latency is high, reduce `bitrate_kbps` in the admin panel (e.g., from 16000 to 8000) and lower `framerate` (e.g., to 30).

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

### Custom Selkies Version

To use a different Selkies build (e.g., a newer release or custom build):

1. Set `SELKIES_TARBALL_URL` to the download URL.
2. Or, download the tarball manually and place it at `{ARTIFACT_CACHE_DIR}/selkies.tar.gz` on the server.
3. Re-enroll workstations.

**Note:** The agent code assumes the tarball contains `selkies-gstreamer-run` as the launcher and specific environment variable names (`SELKIES_PORT`, `SELKIES_ENCODER`, etc.). If the tarball structure or naming differs, update `build_selkies_cmd` in `agent/styx_agent.py`.

### TLS Pinning

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
Last heartbeat timestamp, status (ok/failed), and error message (if failed).

**Selkies streaming logs:**
```
~/.local/share/styx-agent/logs/selkies.log
```
GStreamer output, encoder diagnostics, and WebRTC connection info.

**systemd user service logs:**
```bash
journalctl --user -u styx-agent -n 50
```
Agent daemon startup, crashes, and restarts.

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
- **Single display per machine:** The agent streams one display per machine. For multi-monitor setups, use a virtual compositor or extended desktop.
- **Wayland limitation:** The agent cannot mirror an existing Wayland desktop (upstream Selkies limitation). It runs a separate session instead.
- **Filemode:** Selkies streams the visual desktop only; no file transfer or terminal is provided. Use file sharing (NFS, Samba) or SSH for files.
- **Performance:** Streaming quality depends on network bandwidth, encoder choice, and the machine's GPU availability. Start with default settings and adjust as needed.

---

## Support

For issues:
1. Run `python3 ~/.local/share/styx-agent/styx_agent.py doctor` on the workstation.
2. Check logs (`tail -50 ~/.local/share/styx-agent/logs/selkies.log`).
3. Check the admin panel for the workstation's "Last error" field.
4. Review the error codes above (E00–E08).
5. Check server logs for rejected heartbeats or registration errors.

For Selkies-specific issues (black screen, encoder errors, WebRTC negotiation), see the [Selkies GitHub repository](https://github.com/selkies-project/selkies-gstreamer).
