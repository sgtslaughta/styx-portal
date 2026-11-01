#!/usr/bin/env bash
# Regenerate docs/assets/screens/*.png from the isolated e2e stack (demo data only).
# Usage: e2e/docs-shots/run.sh        KEEP=1 leaves the stack running afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
DC=(docker compose -p styx-e2e -f compose.yml)
[[ "${KEEP:-}" == 1 ]] || trap '"${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true' EXIT
"${DC[@]}" up -d --build --wait --wait-timeout 500
[[ -d node_modules/@playwright ]] || npm ci --no-audit --no-fund
npx playwright install chromium >/dev/null
npx playwright test -c docs-shots.config.ts
python3 docs-shots/optimize.py ../docs/assets/screens  # needs Pillow; skip if absent
