#!/usr/bin/env bash
# Build the prebuilt agent artifacts into the portal's artifact cache.
# Run on the portal server host (needs docker + curl). Re-run to refresh.
# Usage: scripts/build_agent_artifacts.sh [output-dir]   (default ./data/artifacts)
set -euo pipefail

OUT="${1:-./data/artifacts}"
mkdir -p "$OUT"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

SELKIES_COMMIT="0d134b6e1ffe42a579bc66363b0e7159ab22aacc"
SELKIES_URL="https://github.com/selkies-project/selkies/archive/${SELKIES_COMMIT}.tar.gz"
MANYLINUX_IMG="quay.io/pypa/manylinux_2_34_x86_64"
SELKIES_BASEIMAGE="ghcr.io/linuxserver/baseimage-selkies:debiantrixie"
UBU="http://archive.ubuntu.com/ubuntu/pool/main"

echo "==> [1/3] wheelhouse-x86_64.tar.gz (wheels for cp310-cp313)"
# Build/collect every wheel the agent venv needs, per python minor version.
# xkbcommon is source-only on PyPI -> built here so workstations never compile.
docker run --rm -v "$WORK:/out" "$MANYLINUX_IMG" bash -ec '
  yum install -y -q libxkbcommon-devel libxkbcommon
  for PY in cp310-cp310 cp311-cp311 cp312-cp312 cp313-cp313; do
    PIP="/opt/python/$PY/bin/pip"
    "$PIP" -q wheel --wheel-dir /out/wheelhouse \
      "'"$SELKIES_URL"'" pixelflux==1.6.4 pcmflux==1.0.8 \
      setuptools aiohttp pulsectl xkbcommon==0.5
  done
'
tar -C "$WORK" -czf "$OUT/wheelhouse-x86_64.tar.gz" wheelhouse
echo "    $(ls "$WORK/wheelhouse" | wc -l) wheels"

echo "==> [2/3] selkies-web.tar.gz (dashboard dist from linuxserver image)"
docker pull -q "$SELKIES_BASEIMAGE"
docker run --rm -v "$WORK:/out" "$SELKIES_BASEIMAGE" cp -r /usr/share/selkies/web /out/
tar -C "$WORK" -czf "$OUT/selkies-web.tar.gz" web

echo "==> [3/3] libshim-x86_64.tar.gz (libva 2.22 + libwayland-server 1.23)"
mkdir -p "$WORK/shim/lib"
for deb in \
  "libv/libva/libva2_2.22.0-3ubuntu3_amd64.deb" \
  "libv/libva/libva-drm2_2.22.0-3ubuntu3_amd64.deb" \
  "w/wayland/libwayland-server0_1.23.1-3_amd64.deb"; do
  curl -fsSL "$UBU/$deb" -o "$WORK/shim/pkg.deb"
  (cd "$WORK/shim" && ar x pkg.deb \
    && { tar xf data.tar.zst 2>/dev/null || tar xf data.tar.xz; } \
    && cp -a usr/lib/x86_64-linux-gnu/*.so.* lib/ \
    && rm -rf usr control.tar.* data.tar.* debian-binary pkg.deb)
done
tar -C "$WORK/shim" -czf "$OUT/libshim-x86_64.tar.gz" lib

echo "Done. Artifacts in $OUT:"
ls -lh "$OUT"/wheelhouse-x86_64.tar.gz "$OUT"/selkies-web.tar.gz "$OUT"/libshim-x86_64.tar.gz
