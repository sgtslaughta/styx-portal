#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Error: .env file not found. Copy .env.example to .env and fill in values."
    exit 1
fi

set -a
source "$PROJECT_DIR/.env"
set +a

envsubst < "$PROJECT_DIR/traefik/dynamic.yml.tmpl" > "$PROJECT_DIR/traefik/dynamic.yml"
echo "Generated traefik/dynamic.yml with AUTHENTIK_HOST=$AUTHENTIK_HOST"
