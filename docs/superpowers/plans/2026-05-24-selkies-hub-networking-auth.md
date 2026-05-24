# Selkies Hub Networking & Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure Traefik reverse proxy (HTTP-only behind Cloudflare tunnel) with Authentik ForwardAuth middleware for all Selkies Hub services.

**Architecture:** Cloudflare terminates TLS at edge. Tunnel delivers HTTP to Traefik on port 80. Traefik uses file provider for global ForwardAuth middleware pointing to external Authentik outpost. Docker provider auto-discovers containers via labels.

**Tech Stack:** Traefik v3, Cloudflare Tunnel, Authentik (external), Docker Compose, bash/envsubst

**Spec:** `docs/superpowers/specs/2026-05-24-selkies-hub-networking-auth-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `traefik/traefik.yml` | Traefik static config (entrypoints, providers) |
| `traefik/dynamic.yml.tmpl` | ForwardAuth middleware template |
| `scripts/generate-config.sh` | Generates dynamic.yml from .env |
| `docker-compose.yml` | All service definitions and labels |
| `.env.example` | Environment variable documentation |
| `backend/app/services/traefik_labels.py` | Label generator (entrypoint + middleware change) |
| `backend/app/config.py` | New AUTHENTIK_MIDDLEWARE setting |
| `backend/tests/test_traefik_labels.py` | Updated tests |

---

## Task 1: Traefik Static Config

**Files:**
- Modify: `traefik/traefik.yml`

- [ ] **Step 1: Replace traefik.yml**

Replace the entire contents of `traefik/traefik.yml` with:

```yaml
api:
  dashboard: true
  insecure: true

entryPoints:
  web:
    address: ":80"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    network: selkies-hub
    watch: true
  file:
    filename: /etc/traefik/dynamic.yml
    watch: true
```

- [ ] **Step 2: Commit**

```bash
git add traefik/traefik.yml
git commit -m "feat: simplify Traefik config — HTTP-only behind CF tunnel, add file provider"
```

---

## Task 2: ForwardAuth Middleware Template + Generate Script

**Files:**
- Create: `traefik/dynamic.yml.tmpl`
- Create: `scripts/generate-config.sh`

- [ ] **Step 1: Create dynamic.yml.tmpl**

```yaml
# traefik/dynamic.yml.tmpl
# Generated file — do not edit directly. Run scripts/generate-config.sh
http:
  middlewares:
    authentik:
      forwardAuth:
        address: "http://${AUTHENTIK_HOST}/outpost.goauthentication.com/auth/traefik"
        trustForwardHeader: true
        authResponseHeaders:
          - X-Authentik-Username
          - X-Authentik-Groups
          - X-Authentik-Email
          - X-Authentik-Name
          - X-Authentik-Uid
```

- [ ] **Step 2: Create generate-config.sh**

```bash
#!/bin/bash
# scripts/generate-config.sh
# Generates traefik/dynamic.yml from template using .env values
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
```

- [ ] **Step 3: Make script executable**

```bash
chmod +x scripts/generate-config.sh
```

- [ ] **Step 4: Add dynamic.yml to .gitignore**

Append to `.gitignore`:
```
traefik/dynamic.yml
```

- [ ] **Step 5: Commit**

```bash
git add traefik/dynamic.yml.tmpl scripts/generate-config.sh .gitignore
git commit -m "feat: ForwardAuth middleware template and config generator script"
```

---

## Task 3: Update docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Replace docker-compose.yml**

```yaml
networks:
  selkies-hub:
    name: selkies-hub
    driver: bridge

volumes:
  db-data:
  screenshots:

services:
  traefik:
    image: traefik:v3.2
    restart: unless-stopped
    ports:
      - "80:80"
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./traefik/traefik.yml:/etc/traefik/traefik.yml:ro
      - ./traefik/dynamic.yml:/etc/traefik/dynamic.yml:ro
    networks:
      - selkies-hub
    labels:
      - traefik.enable=true
      - traefik.http.routers.dashboard.rule=Host(`traefik.${DOMAIN}`)
      - traefik.http.routers.dashboard.entrypoints=web
      - traefik.http.routers.dashboard.middlewares=authentik@file
      - traefik.http.routers.dashboard.service=api@internal

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel run
    environment:
      - TUNNEL_TOKEN=${CF_TUNNEL_TOKEN}
    networks:
      - selkies-hub

  backend:
    build: ./backend
    restart: unless-stopped
    depends_on:
      - traefik
    environment:
      - DOMAIN=${DOMAIN}
      - DATABASE_URL=sqlite+aiosqlite:///./data/selkies-hub.db
      - DOCKER_NETWORK=selkies-hub
      - TEMPLATES_DIR=/app/templates
      - AUTHENTIK_MIDDLEWARE=authentik@file
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - db-data:/app/data
      - screenshots:/app/data/screenshots
      - ./templates:/app/templates:ro
    networks:
      - selkies-hub
    labels:
      - traefik.enable=true
      - traefik.http.routers.api.rule=Host(`api.${DOMAIN}`)
      - traefik.http.routers.api.entrypoints=web
      - traefik.http.routers.api.middlewares=authentik@file
      - traefik.http.services.api.loadbalancer.server.port=8000

  frontend:
    build: ./frontend
    restart: unless-stopped
    depends_on:
      - backend
    networks:
      - selkies-hub
    labels:
      - traefik.enable=true
      - traefik.http.routers.frontend.rule=Host(`${DOMAIN}`)
      - traefik.http.routers.frontend.entrypoints=web
      - traefik.http.routers.frontend.middlewares=authentik@file
      - traefik.http.services.frontend.loadbalancer.server.port=3000
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: update compose — HTTP entrypoint, ForwardAuth middleware, screenshots volume"
```

---

## Task 4: Update .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Replace .env.example**

```env
# Selkies Hub Configuration
DOMAIN=yourdomain.com
CF_TUNNEL_TOKEN=your-cloudflare-tunnel-token

# Authentik ForwardAuth
AUTHENTIK_HOST=auth.yourdomain.com

# Backend
DATABASE_URL=sqlite+aiosqlite:///./data/selkies-hub.db
DOCKER_NETWORK=selkies-hub
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "feat: add AUTHENTIK_HOST to env example"
```

---

## Task 5: Update Traefik Label Generator

**Files:**
- Modify: `backend/app/services/traefik_labels.py`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_traefik_labels.py`

- [ ] **Step 1: Update tests first**

Replace `backend/tests/test_traefik_labels.py`:

```python
from app.services.traefik_labels import generate_traefik_labels


def test_basic_labels():
    labels = generate_traefik_labels(
        instance_id="abc123",
        subdomain="dev",
        domain="example.com",
        port=3001,
        template_name="dev-desktop",
    )
    assert labels["traefik.enable"] == "true"
    assert labels["traefik.http.routers.abc123.rule"] == "Host(`dev.example.com`)"
    assert labels["traefik.http.routers.abc123.entrypoints"] == "web"
    assert labels["traefik.http.services.abc123.loadbalancer.server.port"] == "3001"
    assert labels["traefik.http.routers.abc123.middlewares"] == "authentik@file"
    assert labels["selkies-hub.managed"] == "true"
    assert labels["selkies-hub.instance-id"] == "abc123"
    assert labels["selkies-hub.template"] == "dev-desktop"


def test_labels_custom_middleware():
    labels = generate_traefik_labels(
        instance_id="xyz",
        subdomain="work",
        domain="my.site",
        port=3001,
        template_name="workstation",
        auth_middleware="custom-auth@file",
    )
    assert labels["traefik.http.routers.xyz.middlewares"] == "custom-auth@file"


def test_labels_custom_port():
    labels = generate_traefik_labels(
        instance_id="id1",
        subdomain="custom",
        domain="d.com",
        port=8080,
        template_name="custom",
    )
    assert labels["traefik.http.services.id1.loadbalancer.server.port"] == "8080"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_traefik_labels.py -v`
Expected: FAIL — `test_basic_labels` expects `web` but gets `websecure`, expects middleware always present

- [ ] **Step 3: Add AUTHENTIK_MIDDLEWARE to config**

Add to `backend/app/config.py` Settings class:

```python
AUTHENTIK_MIDDLEWARE: str = "authentik@file"
```

- [ ] **Step 4: Update traefik_labels.py**

Replace `backend/app/services/traefik_labels.py`:

```python
def generate_traefik_labels(
    instance_id: str,
    subdomain: str,
    domain: str,
    port: int,
    template_name: str,
    auth_middleware: str = "authentik@file",
) -> dict[str, str]:
    return {
        "traefik.enable": "true",
        f"traefik.http.routers.{instance_id}.rule": f"Host(`{subdomain}.{domain}`)",
        f"traefik.http.routers.{instance_id}.entrypoints": "web",
        f"traefik.http.routers.{instance_id}.middlewares": auth_middleware,
        f"traefik.http.services.{instance_id}.loadbalancer.server.port": str(port),
        "selkies-hub.managed": "true",
        "selkies-hub.instance-id": instance_id,
        "selkies-hub.template": template_name,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_traefik_labels.py -v`
Expected: 3 passed

- [ ] **Step 6: Run full test suite**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/traefik_labels.py backend/app/config.py backend/tests/test_traefik_labels.py
git commit -m "feat: update label generator — web entrypoint, always include auth middleware"
```

---

## Task 6: Update CHANGELOG and Final Verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Verify config files are valid YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('traefik/traefik.yml')); print('traefik.yml: OK')"`
Run: `python3 -c "import yaml; yaml.safe_load(open('traefik/dynamic.yml.tmpl')); print('template: OK')"`
Expected: Both print OK

- [ ] **Step 3: Update CHANGELOG.md**

Add above the `## [0.2.0]` entry:

```markdown
## [0.3.0] - 2026-05-24

### Added
- Traefik reverse proxy config for HTTP-only operation behind Cloudflare tunnel
- Authentik ForwardAuth middleware (file provider) for global authentication
- Config generator script (`scripts/generate-config.sh`) for Traefik dynamic config
- ForwardAuth middleware template with Authentik outpost integration

### Changed
- Traefik entrypoint from `websecure` (443) to `web` (80) — TLS handled by Cloudflare
- All service labels updated to use `web` entrypoint and `authentik@file` middleware
- Label generator always includes auth middleware (was optional)
- docker-compose.yml simplified — removed TLS cert volume, added screenshots volume

```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "chore: v0.3.0 changelog — networking and auth layer"
```
