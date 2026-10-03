#!/usr/bin/env bash
# Build the prebuilt agent artifacts into the portal's artifact cache.
# Run on the portal server host (needs docker + curl). Re-run to refresh.
# Usage: scripts/build_agent_artifacts.sh [output-dir]   (default ./data/artifacts)
set -euo pipefail

OUT="${1:-./data/artifacts}"
mkdir -p "$OUT"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK" 2>/dev/null || sudo rm -rf "$WORK" 2>/dev/null || true' EXIT

# Docker images pinned by digest (tag shown for reference; re-pinning requires digest update)
MANYLINUX_IMG="quay.io/pypa/manylinux_2_34_x86_64@sha256:fab7c428345081656cfe4bd5dfa5228b8ce276f0da2c22b470a29134056398c3"  # tag: latest

# Pinned wheel versions (resolved from last successful build; wheelhouse is the lock artifact)
SETUPTOOLS_VER="82.0.1"
AIOHTTP_VER="3.14.1"
PULSECTL_VER="24.12.0"

echo "==> [1/2] wheelhouse-x86_64.tar.gz (wheels for cp310-cp314)"
# Collect every wheel the agent venv needs (selkies 2.0 + transitive deps from
# PyPI), per python minor version, so workstations never compile.
docker run --rm -v "$WORK:/out" "$MANYLINUX_IMG" bash -ec '
  for PY in cp310-cp310 cp311-cp311 cp312-cp312 cp313-cp313 cp314-cp314; do
    PIP="/opt/python/$PY/bin/pip"
    "$PIP" -q wheel --wheel-dir /out/wheelhouse \
      selkies==2.0.0 pixelflux==2.1.0 pcmflux==2.1.0 \
      setuptools=='"$SETUPTOOLS_VER"' aiohttp=='"$AIOHTTP_VER"' pulsectl=='"$PULSECTL_VER"'
  done
'
tar -C "$WORK" -czf "$OUT/wheelhouse-x86_64.tar.gz" wheelhouse
echo "    $(ls "$WORK/wheelhouse" | wc -l) wheels"

echo "==> [2/2] nwg-shell-x86_64.tar.gz (nwg-drawer app grid, Go+GTK build)"
# Built in a golang container (no Go/GTK toolchain on the server host). Only
# nwg-drawer is shipped: it's the app-grid launcher and works on any wlroots
# compositor. nwg-dock is deliberately NOT built — it is sway-only (needs
# SWAYSOCK) and fatals under labwc; the seat uses a bottom waybar as its dock.
# Pinned to the last GTK3 release (v0.6+ moved to gotk4 + gtk4-layer-shell,
# whose runtime libs are absent from Ubuntu 24.04). GTK3 + gtk-layer-shell
# runtime IS present (enroll apt-installs libgtk-layer-shell0).
NWG_DRAWER_TAG="v0.5.2"   # last GTK3 (gotk3) release; v0.6+ is GTK4
mkdir -p "$WORK/bin"
docker run --rm -v "$WORK/bin:/out" golang:1.25-bookworm bash -ec '
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends \
    libgtk-3-dev libgtk-layer-shell-dev libgirepository1.0-dev libcairo2-dev \
    libgdk-pixbuf-2.0-dev libglib2.0-dev pkg-config gcc git
  export CGO_ENABLED=1 GOBIN=/out GOFLAGS=-trimpath
  go install github.com/nwg-piotr/nwg-drawer@'"$NWG_DRAWER_TAG"'
'
chmod 0755 "$WORK/bin/"*
tar -C "$WORK" -czf "$OUT/nwg-shell-x86_64.tar.gz" bin
echo "    $(ls "$WORK/bin" | tr '\n' ' ')"

echo "Done. Artifacts in $OUT:"
ls -lh "$OUT"/wheelhouse-x86_64.tar.gz "$OUT"/nwg-shell-x86_64.tar.gz

# The backend serves artifacts from the `db-data` named volume at
# /app/data/artifacts, NOT this host dir — so a rebuild is invisible until the
# files are copied into the running container. Do it automatically if it's up.
BACKEND_CID=$(docker compose ps -q backend 2>/dev/null || true)
if [ -n "$BACKEND_CID" ]; then
  echo "==> copying artifacts into running backend ($BACKEND_CID)"
  for art in wheelhouse-x86_64 nwg-shell-x86_64; do
    docker cp "$OUT/$art.tar.gz" "$BACKEND_CID:/app/data/artifacts/$art.tar.gz"
  done
  docker exec "$BACKEND_CID" chown -R appuser:appuser /app/data/artifacts
  echo "    backend now serves the rebuilt artifacts"
else
  echo "NOTE: backend container not running. When it is, copy these into the"
  echo "      db-data volume: docker compose cp $OUT/<art>.tar.gz backend:/app/data/artifacts/"
fi
