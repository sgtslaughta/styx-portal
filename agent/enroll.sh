#!/usr/bin/env bash
# Styx Portal workstation enrollment.
# Usage: curl -fsSL https://SERVER/api/enroll/script | bash -s -- \
#          --token <TOKEN> --server https://SERVER [--ca-pin sha256:<FP>]
set -euo pipefail

TOKEN="" SERVER="" CA_PIN="" FORCE_DISPLAY="" FORCE_MODE="auto"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --token)   TOKEN="$2"; shift 2 ;;
    --server)  SERVER="$2"; shift 2 ;;
    --ca-pin)  CA_PIN="$2"; shift 2 ;;
    # Capture this existing X display instead of auto-detecting (e.g. a
    # KasmVNC/Xvnc :1 under a Wayland login). Implies x11 capture.
    --display) FORCE_DISPLAY="$2"; shift 2 ;;
    --mode)    FORCE_MODE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$TOKEN" && -n "$SERVER" ]] || {
  echo "E00: --token and --server are required." >&2; exit 2; }
if [[ "$FORCE_MODE" != "auto" && "$FORCE_MODE" != "mirror" && "$FORCE_MODE" != "seat" ]]; then
  echo "E00: --mode must be auto, mirror, or seat (got: $FORCE_MODE)" >&2; exit 2
fi
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

step 1/8 "Checking system requirements (E01)"
command -v curl >/dev/null 2>&1 || fail E01 "curl not found. Install it (apt install curl / dnf install curl)."
command -v tar  >/dev/null 2>&1 || fail E01 "tar not found. Install it (apt install tar)."
[[ -z "$CA_PIN" ]] || command -v openssl >/dev/null 2>&1 \
  || fail E01 "openssl not found (needed for --ca-pin). Install it (apt install openssl)."
command -v python3 >/dev/null 2>&1 || fail E01 "python3 not found. Install it (apt install python3 / dnf install python3)."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || fail E01 "python3 >= 3.10 required (found $(python3 -V)). Upgrade python3."
python3 -c 'import venv' 2>/dev/null || fail E01 "python3-venv not found. Install it (apt install python3-venv / dnf install python3-venv)."
# Wheels + venv + web dist need ~1.5 GB; require 2 GB headroom.
FREE_MB=$(df -Pm "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
if [[ -n "${FREE_MB:-}" ]] && (( FREE_MB < 2048 )); then
  fail E01 "Less than 2 GB free in $HOME (${FREE_MB} MB). Free up space and re-run."
fi
# awk consumes the whole stream (unlike `head`, which closes the pipe early
# and trips SIGPIPE under pipefail); $2 of the first line is glibc's version.
GLIBC=$(ldd --version 2>/dev/null | awk 'NR==1{for(i=NF;i>=1;i--) if($i ~ /^[0-9]+\.[0-9]+/){print $i; break}}')
GLIBC=${GLIBC:-0.0}
python3 - "$GLIBC" <<'PY' || fail E01 "glibc >= 2.34 required (found $GLIBC) — Ubuntu 22.04+/Debian 12+/RHEL 9+. The pixelflux wheels do not support older distros."
import sys
parts = sys.argv[1].split(".")
try:
    maj, mino = int(parts[0]), int(parts[1])
except (ValueError, IndexError):
    sys.exit(1)
sys.exit(0 if (maj, mino) >= (2, 34) else 1)
PY
note "python3 + glibc $GLIBC OK"

step 2/8 "Choosing capture mode (E02)"
SESSION_TYPE="${XDG_SESSION_TYPE:-}"
[[ -z "$SESSION_TYPE" ]] && command -v loginctl >/dev/null && \
  SESSION_TYPE=$(loginctl show-session "$(loginctl --no-legend 2>/dev/null | awk '$3=="'"$USER"'"{print $1; exit}')" -p Type --value 2>/dev/null || true)
# shellcheck disable=SC2012
X_DISPLAYS=$(ls /tmp/.X11-unix/ 2>/dev/null | sed -n 's/^X\([0-9]\+\)$/:\1/p' | tr '\n' ' ')
if [[ -n "$FORCE_DISPLAY" ]]; then
  MODE="mirror"
elif [[ "$FORCE_MODE" != "auto" ]]; then
  MODE="$FORCE_MODE"
elif [[ "$SESSION_TYPE" == "x11" && -n "${DISPLAY:-}" ]]; then
  MODE="mirror"; FORCE_DISPLAY="$DISPLAY"
else
  MODE="seat"   # wayland session or headless: pixelflux runs its own seat
fi
if [[ "$MODE" == "mirror" ]]; then
  [[ -n "$FORCE_DISPLAY" ]] || { [[ -n "$X_DISPLAYS" ]] && FORCE_DISPLAY="${X_DISPLAYS%% *}"; }
  [[ -n "$FORCE_DISPLAY" ]] || fail E02 "Mirror mode needs an X display; none found. Use --mode seat instead."
  DISPLAY_SERVER="x11"
  note "Mirror mode — duplicating live X display $FORCE_DISPLAY (your session keeps control)."
else
  DISPLAY_SERVER="wayland"
  note "Second-seat mode — a private GPU desktop with this machine's apps and files."
  note "(Your physical screen is not mirrored; Wayland sessions cannot be captured.)"
fi

# Server checks come BEFORE any sudo install so a bad token/URL leaves the
# system untouched.
step 3/8 "Checking server reachability (E05/E06)"
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

step 4/8 "Checking audio stack (E04)"
if command -v pipewire >/dev/null || command -v pulseaudio >/dev/null || pactl info >/dev/null 2>&1; then
  note "audio OK"
else
  fail E04 "Neither PipeWire nor PulseAudio found. Install one (apt install pipewire) for audio streaming."
fi
# pulsectl (agent audio plumbing) binds libpulse via ctypes; PipeWire-only
# minimal installs can lack it.
if ! ldconfig -p 2>/dev/null | grep -q 'libpulse\.so\.0'; then
  note "WARNING (E04): libpulse.so.0 not found — audio may fail. Install it (apt install libpulse0 / dnf install pulseaudio-libs)."
fi

step 5/8 "Installing desktop + GPU dependencies (E03)"
# Detect the package manager and install what each mode needs. Seat mode
# needs labwc (Wayland WM) + wl-clipboard; both modes benefit from VAAPI (AMD/Intel HW
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
# Per-manager package names (VAAPI pkg names differ across distros).
# Seat desktop: WM + Xwayland (X11 apps incl. Chrome) + panel + wallpaper + terminal.
declare -A SEAT_PKG=( [apt]="labwc xwayland waybar swaybg foot wl-clipboard" [dnf]="labwc xorg-x11-server-Xwayland waybar swaybg foot wl-clipboard" [pacman]="labwc xorg-xwayland waybar swaybg foot wl-clipboard" [zypper]="labwc xwayland waybar swaybg foot wl-clipboard" )
declare -A VAAPI_PKG=( [apt]="mesa-va-drivers" [dnf]="mesa-va-drivers" [pacman]="libva-mesa-driver" [zypper]="libva" )
MGR=""
for m in apt dnf pacman zypper; do
  command -v "$m" >/dev/null 2>&1 && { MGR="$m"; break; }
done
if [[ -z "$MGR" ]]; then
  note "WARNING (E03): unknown package manager. Install manually: labwc, wl-clipboard, GPU drivers."
else
  WANT="${VAAPI_PKG[$MGR]}"
  [[ "$MODE" == "seat" ]] && WANT="$WANT ${SEAT_PKG[$MGR]}"
  # shellcheck disable=SC2086  # deliberate word-splitting of the package list
  if install_pkgs "$MGR" $WANT; then
    note "dependencies installed via $MGR"
  else
    note "WARNING (E03): dependency install failed. For seat mode install"
    note "  labwc + wl-clipboard manually, then restart styx-agent."
  fi
fi

GPU_VENDOR="none"
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  GPU_VENDOR="nvidia"; note "NVIDIA GPU — NVENC hardware encoding"
elif [[ -e /dev/dri/renderD128 ]]; then
  GPU_VENDOR="vaapi"; note "GPU render node — VA-API hardware encoding"
else
  note "No GPU encoder detected — using CPU x264 (works; higher latency)."
fi
id -nG | grep -qw render || note "Note: user not in 'render' group — for HW encode: sudo usermod -aG render $USER && re-login"

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

step 7/8 "Installing agent (venv + wheels from portal cache)"
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$UNIT_DIR" "$INSTALL_DIR/logs"
for pair in "agent.py styx_agent.py" "engine.py engine.py" \
            "gateway.py gateway.py" "selkies_launcher.py selkies_launcher.py" \
            "uninstall uninstall.sh"; do
  read -r remote local_name <<<"$pair"
  fetch "$SERVER/api/enroll/$remote" -o "$INSTALL_DIR/$local_name" \
    || fail E05 "Could not download $remote from $SERVER/api/enroll/. Server may be mid-restart or missing its ./agent mount (AGENT_DIR) — retry, then check server logs."
done
chmod +x "$INSTALL_DIR/uninstall.sh"

note "downloading wheels + web dist + lib shim (cached on server)…"
for art in wheelhouse-x86_64.tar.gz selkies-web.tar.gz libshim-x86_64.tar.gz; do
  fetch "$SERVER/api/enroll/artifacts/$art" -o "$INSTALL_DIR/$art" \
    || fail E05 "Artifact $art unavailable. On the server run scripts/build_agent_artifacts.sh (see docs/WORKSTATIONS.md)."
done
for art in wheelhouse-x86_64 selkies-web libshim-x86_64; do
  tar -xzf "$INSTALL_DIR/$art.tar.gz" -C "$INSTALL_DIR" \
    || fail E03 "Extracting $art.tar.gz failed — corrupt download or out of disk. Re-run enrollment."
done

note "creating venv (system python, prebuilt wheels only — no compiling)…"
# The wheelhouse already contains a `selkies` wheel built from the pinned
# tarball, so install everything by name with --no-index — nothing is ever
# compiled on the workstation.
python3 -m venv "$INSTALL_DIR/venv" \
  || fail E01 "venv creation failed — check python3-venv is installed and $HOME has free space."
"$INSTALL_DIR/venv/bin/pip" -q install --no-index \
  --find-links "$INSTALL_DIR/wheelhouse" \
  selkies pixelflux==1.6.4 pcmflux setuptools aiohttp pulsectl \
  || fail E03 "Wheel install failed — likely an unsupported python version ($(python3 -V)). The wheelhouse covers python 3.10–3.13."
rm -rf "$INSTALL_DIR/wheelhouse" "$INSTALL_DIR"/*.tar.gz

step 8/8 "Registering with portal"
SERVER_HOST="${SERVER#http*://}"; SERVER_HOST="${SERVER_HOST%%/*}"; SERVER_HOST="${SERVER_HOST%%:*}"
LAN_IP=$(ip route get "$SERVER_HOST" 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')

# One-time hardware/OS report for the admin UI (model names; counts; sizes).
GPU_MODEL=""
if [[ "$GPU_VENDOR" == "nvidia" ]]; then
  GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | awk 'NR==1' || true)
elif command -v lspci >/dev/null 2>&1; then
  GPU_MODEL=$(lspci 2>/dev/null | awk -F': ' '/VGA compatible controller|3D controller|Display controller/{print $NF; exit}' || true)
fi

PAYLOAD=$(python3 - "$TOKEN" "$LAN_IP" "$DISPLAY_SERVER" "$GPU_VENDOR" "$GPU_MODEL" "$MODE" <<'PY'
import json, os, platform, shutil, sys

def cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or ""

def memory_mb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0

try:
    osr = platform.freedesktop_os_release()
except (OSError, AttributeError):
    osr = {}
du = shutil.disk_usage(os.path.expanduser("~"))
print(json.dumps({
    "token": sys.argv[1], "hostname": platform.node() or "workstation",
    "lan_ip": sys.argv[2], "display_server": sys.argv[3],
    "gpu_info": {"vendor": sys.argv[4], "model": sys.argv[5]},
    "os_info": {
        "distro": osr.get("ID", "unknown"),
        "pretty_name": osr.get("PRETTY_NAME", ""),
        "version": osr.get("VERSION_ID", ""),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "cpu_model": cpu_model(),
        "cpu_cores": os.cpu_count() or 0,
        "memory_mb": memory_mb(),
        "disk_total_gb": round(du.total / 1e9),
        "disk_free_gb": round(du.free / 1e9),
        "mode": sys.argv[6],
    },
    "agent_version": "0.4.1"}))
PY
) || fail E01 "Could not gather system info (python error above)."

# Plain curl (not fetch -f) so an HTTP error still yields the body — the
# server's "detail" explains WHY registration was rejected.
BODY_FILE=$(mktemp)
CURL_CA=()
[[ -n "$PINNED_CERT" ]] && CURL_CA=(--cacert "$PINNED_CERT")
HTTP_CODE=$(curl -sS "${CURL_CA[@]}" -o "$BODY_FILE" -w '%{http_code}' \
  -X POST -H "Content-Type: application/json" -d "$PAYLOAD" \
  "$SERVER/api/enroll/register") \
  || { rm -f "$BODY_FILE"; fail E05 "Lost connection to $SERVER during registration. Check the network and re-run."; }
REGISTER_RESPONSE=$(cat "$BODY_FILE"); rm -f "$BODY_FILE"
if [[ "$HTTP_CODE" != "201" ]]; then
  DETAIL=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("detail", ""))' \
    "$REGISTER_RESPONSE" 2>/dev/null || true)
  fail E05 "Registration rejected (HTTP $HTTP_CODE${DETAIL:+ — $DETAIL}). If the token expired or was already used, mint a new one in the admin Workstations panel."
fi

python3 - "$REGISTER_RESPONSE" "$SERVER" "$CA_PIN" "$DISPLAY_SERVER" "$INSTALL_DIR" "$CONFIG_DIR" "$FORCE_DISPLAY" "$MODE" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
cfg = {"server": sys.argv[2], "agent_token": r["agent_token"],
       "workstation_id": r["workstation_id"], "port": r["port"],
       "selkies_user": r["selkies_user"], "selkies_password": r["selkies_password"],
       "mode": sys.argv[8], "display": sys.argv[7] or "",
       "stream_settings": r["stream_settings"],
       "install_dir": sys.argv[5], "ca_pin": sys.argv[3],
       "server_cert": (sys.argv[6] + "/server-cert.pem") if sys.argv[3] else ""}
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
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/styx_agent.py run
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
echo "  Troubleshoot:  $INSTALL_DIR/venv/bin/python $INSTALL_DIR/styx_agent.py doctor"
echo "  Uninstall:     bash $INSTALL_DIR/uninstall.sh"
