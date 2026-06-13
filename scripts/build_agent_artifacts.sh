#!/usr/bin/env bash
# Build the prebuilt agent artifacts into the portal's artifact cache.
# Run on the portal server host (needs docker + curl). Re-run to refresh.
# Usage: scripts/build_agent_artifacts.sh [output-dir]   (default ./data/artifacts)
set -euo pipefail

OUT="${1:-./data/artifacts}"
mkdir -p "$OUT"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK" 2>/dev/null || sudo rm -rf "$WORK" 2>/dev/null || true' EXIT

SELKIES_COMMIT="0d134b6e1ffe42a579bc66363b0e7159ab22aacc"
SELKIES_URL="https://github.com/selkies-project/selkies/archive/${SELKIES_COMMIT}.tar.gz"

# Docker images pinned by digest (tag shown for reference; re-pinning requires digest update)
MANYLINUX_IMG="quay.io/pypa/manylinux_2_34_x86_64@sha256:fab7c428345081656cfe4bd5dfa5228b8ce276f0da2c22b470a29134056398c3"  # tag: latest
SELKIES_BASEIMAGE="ghcr.io/linuxserver/baseimage-selkies@sha256:2468327691fd63ff8be8e14e0ba1bcea0dedb4715502c6e22cc210d5575b6632"  # tag: debiantrixie

# Ubuntu pool base URL (https only)
UBU="https://archive.ubuntu.com/ubuntu/pool/main"

# Deb packages with pinned SHA256 hashes (verified: 2026-06-11)
declare -A DEB_SHA256=(
  [libva2_2.22.0-3ubuntu3_amd64.deb]="629b6ac0d12f7f9ec32be401c52b19231eb1bfed83ad8a814b2b93af1533726d"
  [libva-drm2_2.22.0-3ubuntu3_amd64.deb]="bdf1f908b5c2b755b4ee2b4fc226eae10b1c71a54d53d09310834ce4a3c0703b"
  [libwayland-server0_1.23.1-3_amd64.deb]="c5de744d0acf62b0a4bab38631b9ce8b0d0ec20a8f2bcf7b9a1995739cfe1a2c"
)

# Pinned wheel versions (resolved from last successful build; wheelhouse is the lock artifact)
SETUPTOOLS_VER="82.0.1"
AIOHTTP_VER="3.14.1"
PULSECTL_VER="24.12.0"

echo "==> [1/4] wheelhouse-x86_64.tar.gz (wheels for cp310-cp313)"
# Build/collect every wheel the agent venv needs, per python minor version.
# xkbcommon is source-only on PyPI -> built here so workstations never compile.
docker run --rm -v "$WORK:/out" "$MANYLINUX_IMG" bash -ec '
  yum install -y -q libxkbcommon-devel libxkbcommon
  for PY in cp310-cp310 cp311-cp311 cp312-cp312 cp313-cp313; do
    PIP="/opt/python/$PY/bin/pip"
    "$PIP" -q wheel --wheel-dir /out/wheelhouse \
      "'"$SELKIES_URL"'" pixelflux==1.6.4 pcmflux==1.0.8 \
      setuptools=='"$SETUPTOOLS_VER"' aiohttp=='"$AIOHTTP_VER"' pulsectl=='"$PULSECTL_VER"' xkbcommon==0.5
  done
'
tar -C "$WORK" -czf "$OUT/wheelhouse-x86_64.tar.gz" wheelhouse
echo "    $(ls "$WORK/wheelhouse" | wc -l) wheels"

echo "==> [2/4] selkies-web.tar.gz (dashboard dist from linuxserver image)"
docker pull -q "$SELKIES_BASEIMAGE"
docker run --rm -v "$WORK:/out" "$SELKIES_BASEIMAGE" cp -r /usr/share/selkies/web /out/
tar -C "$WORK" -czf "$OUT/selkies-web.tar.gz" web

echo "==> [3/4] libshim-x86_64.tar.gz (libva 2.22 + libwayland-server 1.23)"
mkdir -p "$WORK/shim/lib"
# Download and verify debs with pinned SHA256 hashes
declare -a DEB_PATHS=(
  "libv/libva/libva2_2.22.0-3ubuntu3_amd64.deb"
  "libv/libva/libva-drm2_2.22.0-3ubuntu3_amd64.deb"
  "w/wayland/libwayland-server0_1.23.1-3_amd64.deb"
)
for deb_path in "${DEB_PATHS[@]}"; do
  deb_file=$(basename "$deb_path")
  curl -fsSL "$UBU/$deb_path" -o "$WORK/shim/pkg.deb"

  # Verify SHA256 hash
  expected_hash="${DEB_SHA256[$deb_file]}"
  actual_hash=$(sha256sum "$WORK/shim/pkg.deb" | awk '{print $1}')
  if [ "$actual_hash" != "$expected_hash" ]; then
    echo "ERROR: Hash mismatch for $deb_file"
    echo "  Expected: $expected_hash"
    echo "  Got:      $actual_hash"
    exit 1
  fi

  (cd "$WORK/shim" && ar x pkg.deb \
    && { tar xf data.tar.zst 2>/dev/null || tar xf data.tar.xz; } \
    && cp -a usr/lib/x86_64-linux-gnu/*.so.* lib/ \
    && rm -rf usr control.tar.* data.tar.* debian-binary pkg.deb)
done
tar -C "$WORK/shim" -czf "$OUT/libshim-x86_64.tar.gz" lib

echo "==> [4/4] nwg-shell-x86_64.tar.gz (nwg-drawer app grid, Go+GTK build)"
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
ls -lh "$OUT"/wheelhouse-x86_64.tar.gz "$OUT"/selkies-web.tar.gz \
       "$OUT"/libshim-x86_64.tar.gz "$OUT"/nwg-shell-x86_64.tar.gz
