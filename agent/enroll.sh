#!/usr/bin/env bash
# Styx Portal workstation enrollment.
# Usage: curl -fsSL https://SERVER/api/enroll/script | bash -s -- \
#          --token <TOKEN> --server https://SERVER [--ca-pin sha256:<FP>]
set -euo pipefail

TOKEN="" SERVER="" CA_PIN="" FORCE_DISPLAY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --token)   TOKEN="$2"; shift 2 ;;
    --server)  SERVER="$2"; shift 2 ;;
    --ca-pin)  CA_PIN="$2"; shift 2 ;;
    # Capture this existing X display instead of auto-detecting (e.g. a
    # KasmVNC/Xvnc :1 under a Wayland login). Implies x11 capture.
    --display) FORCE_DISPLAY="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$TOKEN" && -n "$SERVER" ]] || {
  echo "E00: --token and --server are required." >&2; exit 2; }
SERVER="${SERVER%/}"

INSTALL_DIR="$HOME/.local/share/styx-agent"
CONFIG_DIR="$HOME/.config/styx-agent"
UNIT_DIR="$HOME/.config/systemd/user"

fail() { local code="$1"; shift; echo ""; echo "✗ $code: $*" >&2; exit 1; }
note() { echo "  → $*"; }
step() { echo ""; echo "[$1] $2"; }

# curl wrapper: once the server cert is fingerprint-verified (step 5) it is
# saved and used as the pinned CA for every request — no insecure fetches.
PINNED_CERT=""
fetch() {
  if [[ -n "$PINNED_CERT" ]]; then curl -fsS --cacert "$PINNED_CERT" "$@"
  else curl -fsS "$@"; fi
}

step 1/8 "Checking distro and glibc (E01)"
command -v python3 >/dev/null 2>&1 || fail E01 "python3 not found. Install it (apt install python3 / dnf install python3)."
# awk consumes the whole stream (unlike `head`, which closes the pipe early
# and trips SIGPIPE under pipefail); $2 of the first line is glibc's version.
GLIBC=$(ldd --version 2>/dev/null | awk 'NR==1{for(i=NF;i>=1;i--) if($i ~ /^[0-9]+\.[0-9]+/){print $i; break}}')
GLIBC=${GLIBC:-0.0}
python3 - "$GLIBC" <<'PY' || fail E01 "glibc >= 2.17 required (found $GLIBC). Selkies portable build will not run."
import sys
parts = sys.argv[1].split(".")
try:
    maj, mino = int(parts[0]), int(parts[1])
except (ValueError, IndexError):
    sys.exit(1)
sys.exit(0 if (maj, mino) >= (2, 17) else 1)
PY
note "python3 + glibc $GLIBC OK"

step 2/8 "Choosing capture mode (E02)"
# Default: the agent runs its OWN virtual desktop (Xvfb) — uniform across
# headless / X11 / Wayland. --display opts into mirroring an existing X display.
# shellcheck disable=SC2012  # X-socket names are always Xn; ls is fine here
X_DISPLAYS=$(ls /tmp/.X11-unix/ 2>/dev/null | sed -n 's/^X\([0-9]\+\)$/:\1/p' | tr '\n' ' ')
if [[ -n "$FORCE_DISPLAY" ]]; then
  MODE="mirror"; DISPLAY_SERVER="x11"
  note "Mirror mode — streaming existing X display $FORCE_DISPLAY."
else
  MODE="own"; DISPLAY_SERVER="virtual"
  note "Own-desktop mode — the agent runs a private virtual desktop and streams it."
  note "(Streams a fresh session, not this machine's physical screen.)"
  [[ -n "$X_DISPLAYS" ]] && \
    note "To mirror an existing X display instead, re-run with: --display ${X_DISPLAYS%% *}"
fi

step 3/8 "Installing desktop + GPU dependencies (E03)"
# Detect the package manager and install what each mode needs. Own-desktop
# needs Xvfb + a WM + a terminal; both modes benefit from VAAPI (AMD/Intel HW
# encode). This is the one place we touch the system with sudo.
install_pkgs() {
  local mgr="$1"; shift
  case "$mgr" in
    apt)    sudo apt-get update -qq && sudo apt-get install -y --no-install-recommends "$@" ;;
    dnf)    sudo dnf install -y "$@" ;;
    pacman) sudo pacman -Sy --needed --noconfirm "$@" ;;
    zypper) sudo zypper --non-interactive install "$@" ;;
  esac
}
# Per-manager package names (Xvfb + VAAPI pkg names differ across distros).
declare -A XVFB_PKG=( [apt]=xvfb [dnf]=xorg-x11-server-Xvfb [pacman]=xorg-server-xvfb [zypper]=xorg-x11-server-Xvfb )
declare -A VAAPI_PKG=( [apt]="vainfo mesa-va-drivers" [dnf]="libva-utils mesa-va-drivers" [pacman]="libva-utils libva-mesa-driver" [zypper]="libva-utils" )
MGR=""
for m in apt dnf pacman zypper; do
  command -v "$m" >/dev/null 2>&1 && { MGR="$m"; break; }
done
if [[ -z "$MGR" ]]; then
  note "WARNING (E03): unknown package manager. Install manually: Xvfb, openbox, xterm, vainfo."
else
  WANT="${VAAPI_PKG[$MGR]}"
  [[ "$MODE" == "own" ]] && WANT="$WANT ${XVFB_PKG[$MGR]} openbox xterm"
  # shellcheck disable=SC2086  # deliberate word-splitting of the package list
  if install_pkgs "$MGR" $WANT; then
    note "dependencies installed via $MGR"
  else
    note "WARNING (E03): dependency install failed. For own-desktop mode install"
    note "  Xvfb + openbox + xterm manually, then restart styx-agent."
  fi
fi

GPU_VENDOR="none"
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  GPU_VENDOR="nvidia"; note "NVIDIA GPU — NVENC hardware encoding"
elif command -v vainfo >/dev/null && vainfo >/dev/null 2>&1; then
  GPU_VENDOR="vaapi"; note "VAAPI GPU — hardware encoding"
else
  note "No GPU encoder detected — using CPU x264 (works; higher latency)."
fi
id -nG | grep -qw render || note "Note: user not in 'render' group — for HW encode: sudo usermod -aG render $USER && re-login"

step 4/8 "Checking audio stack (E04)"
if command -v pipewire >/dev/null || command -v pulseaudio >/dev/null || pactl info >/dev/null 2>&1; then
  note "audio OK"
else
  fail E04 "Neither PipeWire nor PulseAudio found. Install one (apt install pipewire) for audio streaming."
fi

step 5/8 "Checking server reachability (E05/E06)"
if [[ -n "$CA_PIN" ]]; then
  HOSTPORT="${SERVER#https://}"; HOSTPORT="${HOSTPORT%%/*}"
  HOST="${HOSTPORT%%:*}"; PORT="${HOSTPORT##*:}"; [[ "$PORT" == "$HOST" ]] && PORT=443
  mkdir -p "$CONFIG_DIR"
  PINNED_CERT="$CONFIG_DIR/server-cert.pem"
  echo | openssl s_client -connect "$HOST:$PORT" 2>/dev/null \
    | openssl x509 -outform PEM > "$PINNED_CERT" \
    || fail E06 "Could not read TLS certificate from $HOST:$PORT."
  ACTUAL=$(openssl x509 -in "$PINNED_CERT" -fingerprint -sha256 -noout \
    | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f')
  EXPECTED=$(echo "${CA_PIN#sha256:}" | tr -d ':' | tr 'A-F' 'a-f')
  if [[ "$ACTUAL" != "$EXPECTED" ]]; then
    rm -f "$PINNED_CERT"
    fail E06 "TLS certificate fingerprint mismatch (expected $EXPECTED, got $ACTUAL). Wrong server or MITM."
  fi
  chmod 600 "$PINNED_CERT"
  note "certificate pin verified — pinned cert saved for all further requests"
fi
fetch "$SERVER/api/health" >/dev/null || fail E05 "Cannot reach $SERVER from this machine. Check LAN routing/firewall (this must be the portal's LOCAL address, not the public tunnel)."
note "server reachable"

step 6/8 "Checking port and systemd (E07/E08)"
SELKIES_PORT=8443
# Capture first (no pipe to grep -q, which closes early and trips SIGPIPE
# under pipefail — masking a busy port).
if command -v ss >/dev/null; then
  PORT_LISTEN=$(ss -ltn "sport = :$SELKIES_PORT" 2>/dev/null || true)
  case "$PORT_LISTEN" in
    *LISTEN*) fail E07 "Port $SELKIES_PORT already in use. Free it or change WORKSTATION_DEFAULT_PORT on the server." ;;
  esac
fi
systemctl --user show-environment >/dev/null 2>&1 \
  || fail E08 "systemd --user session unavailable. Log in as this user via a normal session (not su/sudo)."

step 7/8 "Installing agent + Selkies"
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$UNIT_DIR" "$INSTALL_DIR/logs"
fetch "$SERVER/api/enroll/agent.py"  -o "$INSTALL_DIR/styx_agent.py"
fetch "$SERVER/api/enroll/uninstall" -o "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/uninstall.sh"
note "downloading Selkies (cached on server — may take a minute)…"
fetch "$SERVER/api/enroll/artifacts/selkies.tar.gz" -o "$INSTALL_DIR/selkies.tar.gz" \
  || fail E05 "Selkies download failed. On the server, check SELKIES_TARBALL_URL or pre-place the tarball (see docs/WORKSTATIONS.md)."
mkdir -p "$INSTALL_DIR/selkies"
tar -xzf "$INSTALL_DIR/selkies.tar.gz" -C "$INSTALL_DIR/selkies" --strip-components=1
rm -f "$INSTALL_DIR/selkies.tar.gz"

step 8/8 "Registering with portal"
SERVER_HOST="${SERVER#http*://}"; SERVER_HOST="${SERVER_HOST%%/*}"; SERVER_HOST="${SERVER_HOST%%:*}"
LAN_IP=$(ip route get "$SERVER_HOST" 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')
REGISTER_RESPONSE=$(fetch -X POST "$SERVER/api/enroll/register" \
  -H "Content-Type: application/json" \
  -d "$(python3 - "$TOKEN" "$LAN_IP" "$DISPLAY_SERVER" "$GPU_VENDOR" <<'PY'
import json, platform, sys
print(json.dumps({
    "token": sys.argv[1], "hostname": platform.node() or "workstation",
    "lan_ip": sys.argv[2], "display_server": sys.argv[3],
    "gpu_info": {"vendor": sys.argv[4]},
    "os_info": {"distro": platform.freedesktop_os_release().get("ID", "unknown")
                if hasattr(platform, "freedesktop_os_release") else "unknown",
                "kernel": platform.release()},
    "agent_version": "0.3.0"}))
PY
)") || fail E05 "Registration rejected. The token may be expired or already used — mint a new one in the admin Workstations panel."

python3 - "$REGISTER_RESPONSE" "$SERVER" "$CA_PIN" "$DISPLAY_SERVER" "$INSTALL_DIR" "$CONFIG_DIR" "$FORCE_DISPLAY" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
cfg = {"server": sys.argv[2], "agent_token": r["agent_token"],
       "workstation_id": r["workstation_id"], "port": r["port"],
       "selkies_user": r["selkies_user"], "selkies_password": r["selkies_password"],
       "display_server": sys.argv[4], "stream_settings": r["stream_settings"],
       "selkies_dir": sys.argv[5] + "/selkies", "ca_pin": sys.argv[3],
       "server_cert": (sys.argv[6] + "/server-cert.pem") if sys.argv[3] else ""}
if len(sys.argv) > 7 and sys.argv[7]:
    cfg["display"] = sys.argv[7]   # forced X display (e.g. :1)
with open(sys.argv[6] + "/config.json", "w") as f:
    json.dump(cfg, f, indent=2)
print("  → registered as: " + r["subdomain"])
PY
chmod 600 "$CONFIG_DIR/config.json"

cat > "$UNIT_DIR/styx-agent.service" <<EOF
[Unit]
Description=Styx Portal workstation agent (Selkies streaming)
After=network-online.target

[Service]
ExecStart=/usr/bin/env python3 $INSTALL_DIR/styx_agent.py run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now styx-agent.service

if command -v loginctl >/dev/null && [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
  echo ""
  echo "Enabling lingering so streaming survives logout (requires sudo, one time):"
  sudo loginctl enable-linger "$USER" \
    || note "WARNING: lingering not enabled — streaming stops when you log out. Run later: sudo loginctl enable-linger $USER"
fi

echo ""
echo "✓ Enrollment complete. This workstation should appear Online in the portal within 60s."
echo "  Troubleshoot:  python3 $INSTALL_DIR/styx_agent.py doctor"
echo "  Uninstall:     python3 $INSTALL_DIR/styx_agent.py uninstall"
