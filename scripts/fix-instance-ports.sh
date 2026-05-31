#!/usr/bin/env bash
#
# Fix instances that can't connect because their template's internal_port is 443.
#
# Background: LinuxServer.io Selkies/KasmVNC images serve the web UI on 3001 (HTTPS),
# never 443. A detection bug stored internal_port=443 for some templates (e.g. firefox,
# webstation), so Traefik routed /i/<sub> to https://selkies-<sub>:443 (a dead port).
#
# This script:
#   1. Rewrites every template with internal_port=443 to 3001/https.
#   2. Recreates the running instances of those templates (regenerates Traefik routes,
#      reuses named volumes -> data preserved).
#   3. Prints the resulting routes for verification.
#   4. Optionally rebuilds+redeploys the frontend so FUTURE launches use the fixed
#      detection default (pass --rebuild-frontend).
#
# Usage:
#   ./scripts/fix-instance-ports.sh                    # fix data + recreate running instances
#   ./scripts/fix-instance-ports.sh --rebuild-frontend # also redeploy the frontend
#
set -euo pipefail

BACKEND="${BACKEND_CONTAINER:-remote-access-backend-1}"
TRAEFIK="${TRAEFIK_CONTAINER:-remote-access-traefik-1}"

if ! docker inspect "$BACKEND" >/dev/null 2>&1; then
  echo "ERROR: backend container '$BACKEND' not found. Set BACKEND_CONTAINER=<name>." >&2
  exit 1
fi

echo "==> Repairing templates with internal_port=443 using the registry's declared port"
docker exec "$BACKEND" python - <<'PY'
import sqlite3, urllib.request, json, re

DB = "/app/data/selkies-hub.db"
API = "http://localhost:8000/api"


def lsio_name(image: str):
    """lscr.io/linuxserver/firefox:latest -> firefox; non-LSIO -> None."""
    m = re.search(r"(?:lscr\.io/)?linuxserver/([^:@/]+)", image, re.I)
    return m.group(1) if m else None


def registry_port(image: str):
    """Pick the web UI port+protocol from the registry image's declared ports.
    Prefer HTTPS (by desc), then HTTP, then the first port. None if unknown."""
    name = lsio_name(image)
    if not name:
        return None
    try:
        data = json.load(urllib.request.urlopen(f"{API}/registry/images/{name}", timeout=20))
    except Exception:
        return None
    ports = (data.get("config") or {}).get("ports") or []
    https = next((p for p in ports if re.search(r"https", p.get("desc", ""), re.I)), None)
    if https:
        return int(https["internal"]), "https"
    http = next((p for p in ports if re.search(r"http", p.get("desc", ""), re.I)), None)
    if http:
        return int(http["internal"]), "http"
    if ports:
        return int(ports[0]["internal"]), "https"
    return None


conn = sqlite3.connect(DB)
broken = conn.execute(
    "select id, name, image from service_templates where internal_port = 443"
).fetchall()
if not broken:
    print("No templates with internal_port=443. Nothing to fix.")

bad_ids = []
for tid, name, image in broken:
    detected = registry_port(image)
    port, proto = detected if detected else (3001, "https")
    src = "registry" if detected else "fallback"
    conn.execute(
        "update service_templates set internal_port = ?, internal_protocol = ? where id = ?",
        (port, proto, tid),
    )
    bad_ids.append(tid)
    print(f"  {name}: {image} -> {proto}://:{port} ({src})")
conn.commit()
print(f"Templates updated: {conn.total_changes}")

# Recreate only instances that currently have a live container (running/idle).
# Stopped instances pick up the corrected port automatically on next start.
insts = []
if bad_ids:
    placeholders = ",".join("?" * len(bad_ids))
    insts = conn.execute(
        f"select id, name, status from instances "
        f"where template_id in ({placeholders}) and status in ('running','idle')",
        bad_ids,
    ).fetchall()

if not insts:
    print("No running instances of the fixed templates to recreate.")
for iid, name, status in insts:
    try:
        req = urllib.request.Request(f"{API}/instances/{iid}/recreate", method="POST")
        code = urllib.request.urlopen(req, timeout=90).status
        print(f"  recreated {name} ({iid}) [{status}]: HTTP {code}")
    except Exception as e:
        print(f"  FAILED to recreate {name} ({iid}): {e}")
PY

echo
echo "==> Traefik service routes (expect https://selkies-...:3001):"
docker exec "$TRAEFIK" cat /etc/traefik/dynamic/routes.yml 2>/dev/null \
  | grep -E "url: https?://selkies" || echo "  (no selkies routes found)"

if [ "${1:-}" = "--rebuild-frontend" ]; then
  echo
  echo "==> Rebuilding + redeploying frontend (future launches use 3001/https detection)"
  ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
  ( cd "$ROOT" && docker compose build frontend && docker compose up -d frontend )
else
  echo
  echo "==> Skipped frontend rebuild. Re-run with --rebuild-frontend to fix FUTURE launches too."
fi

echo
echo "Done. Reconnect to the recreated instance(s)."
