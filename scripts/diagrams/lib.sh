# Shared: run a node command inside the playwright container with the repo mounted.
IMG=mcr.microsoft.com/playwright:v1.64.1-jammy
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
dnode() { # dnode <script args...>; installs pinned deps on first use, chowns outputs back
  docker run --rm -v "$ROOT":/src -w /src/scripts/diagrams "$IMG" sh -c \
    "[ -d node_modules/.bin ] || npm ci --silent --no-audit --no-fund 2>&1 | tail -3; \
     node $*; rc=\$?; chown -R $(id -u):$(id -g) /src/scripts/diagrams /src/docs/assets/diagrams /src/README.md /src/docs 2>/dev/null; exit \$rc"
}
