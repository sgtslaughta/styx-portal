#!/usr/bin/env bash
# Isolated full-stack e2e for proxied services.
# Builds and starts the `styx-e2e` compose project (only 127.0.0.1:18080 is
# published), runs the Playwright suite, and always tears everything down.
# Usage: e2e/run.sh [playwright args...]   e.g. e2e/run.sh -g "cookie-root"
# KEEP=1 leaves the stack running for debugging (down it yourself later).
set -euo pipefail
cd "$(dirname "$0")"
DC=(docker compose -p styx-e2e -f compose.yml)

cleanup() {
  if [[ "${KEEP:-}" == 1 ]]; then
    echo "KEEP=1: stack left running. Stop it with: ${DC[*]} down -v --remove-orphans"
  else
    "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true  # stale run => fresh DB
"${DC[@]}" up -d --build --wait --wait-timeout 300

[[ -d node_modules/@playwright/test ]] || npm ci --no-audit --no-fund
npx playwright install chromium >/dev/null

rm -rf screenshots && mkdir -p screenshots
status=0
npx playwright test "$@" || status=$?
if [[ $status -ne 0 ]]; then
  mkdir -p test-results
  "${DC[@]}" logs --no-color --tail 200 backend traefik docker-shim > test-results/stack.log 2>&1 || true
  echo "Stack logs: e2e/test-results/stack.log"
fi
exit $status
