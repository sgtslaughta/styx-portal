# Selkies Hub Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the React frontend dashboard for Selkies Hub, plus two backend additions (screenshot endpoint + LinuxServer registry proxy).

**Architecture:** Vite SPA communicating with the existing FastAPI backend. TanStack Query for data fetching with 5s polling. Tab-based layout (Instances / Template Gallery). Backend additions: registry proxy caches LinuxServer API, screenshot service captures container thumbnails.

**Tech Stack:** Vite, React 18, TypeScript, Tailwind CSS 4, shadcn/ui, TanStack Query, Lucide React, React Router v7

**Spec:** `docs/superpowers/specs/2026-05-24-selkies-hub-frontend-design.md`

---

## File Map

### Backend additions

| File | Responsibility |
|------|---------------|
| `backend/app/routers/registry.py` | LinuxServer registry proxy endpoints |
| `backend/app/services/screenshot.py` | Screenshot capture + caching service |
| `backend/tests/test_registry.py` | Registry proxy tests |
| `backend/tests/test_screenshots.py` | Screenshot service tests |

### Frontend

| File | Responsibility |
|------|---------------|
| `frontend/package.json` | Dependencies and scripts |
| `frontend/vite.config.ts` | Vite config with API proxy |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/tsconfig.app.json` | App-specific TS config |
| `frontend/tsconfig.node.json` | Node TS config for Vite |
| `frontend/index.html` | HTML entry point |
| `frontend/postcss.config.js` | PostCSS for Tailwind |
| `frontend/components.json` | shadcn/ui config |
| `frontend/src/main.tsx` | App entry, providers |
| `frontend/src/App.tsx` | Layout shell, routing |
| `frontend/src/styles/globals.css` | Tailwind directives, theme vars |
| `frontend/src/lib/utils.ts` | cn(), formatDuration() helpers |
| `frontend/src/lib/types.ts` | TypeScript interfaces for API |
| `frontend/src/api/client.ts` | Fetch wrapper, base URL |
| `frontend/src/hooks/use-instances.ts` | TanStack Query: instances |
| `frontend/src/hooks/use-templates.ts` | TanStack Query: templates |
| `frontend/src/hooks/use-registry.ts` | TanStack Query: LinuxServer registry |
| `frontend/src/components/ui/` | shadcn components (button, card, dialog, badge, input, tabs, dropdown-menu, separator, sonner) |
| `frontend/src/components/layout/header.tsx` | Logo, status summary, theme toggle |
| `frontend/src/components/layout/tab-nav.tsx` | My Instances / Template Gallery tabs |
| `frontend/src/components/instances/instance-card.tsx` | Instance card with screenshot |
| `frontend/src/components/instances/instance-grid.tsx` | Responsive card grid |
| `frontend/src/components/instances/instance-detail.tsx` | Detail slide-over modal |
| `frontend/src/components/instances/status-badge.tsx` | Colored status indicator |
| `frontend/src/components/templates/template-card.tsx` | Template card (my templates) |
| `frontend/src/components/templates/template-grid.tsx` | Template grid |
| `frontend/src/components/templates/registry-browser.tsx` | LinuxServer registry browser |
| `frontend/src/components/templates/launch-modal.tsx` | Create/launch form |
| `frontend/src/components/templates/env-editor.tsx` | Key/value env var editor |
| `frontend/nginx.conf` | Nginx config for prod |
| `frontend/Dockerfile` | Multi-stage build |

---

## Task 1: Backend — LinuxServer Registry Proxy

**Files:**
- Create: `backend/app/routers/registry.py`
- Create: `backend/tests/test_registry.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write registry proxy tests**

```python
# backend/tests/test_registry.py
from unittest.mock import patch, MagicMock


MOCK_LSIO_RESPONSE = [
    {
        "name": "firefox",
        "description": "Firefox browser in a container",
        "project_logo": "https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/firefox-logo.png",
        "category": "Productivity",
        "stars": 120,
        "monthly_pulls": 500000,
        "version": "v1.0.0-ls50",
        "stable": True,
        "config": {
            "env_vars": [
                {"name": "PUID", "default": "1000", "description": "User ID"},
                {"name": "PGID", "default": "1000", "description": "Group ID"},
            ],
            "volumes": [
                {"container": "/config", "description": "Config directory"}
            ],
            "ports": [
                {"container": "3000", "description": "Web UI"}
            ],
        },
        "architectures": [
            {"arch": "x86_64", "tag": "amd64-latest"}
        ],
        "github_url": "https://github.com/linuxserver/docker-firefox",
        "project_url": "https://www.mozilla.org/firefox/",
    },
    {
        "name": "wireguard",
        "description": "WireGuard VPN",
        "project_logo": "https://example.com/wg.png",
        "category": "Network",
        "stars": 200,
        "monthly_pulls": 800000,
        "version": "v1.0.0-ls10",
        "stable": True,
        "config": {
            "env_vars": [],
            "volumes": [],
            "ports": [],
        },
        "architectures": [],
        "github_url": "https://github.com/linuxserver/docker-wireguard",
        "project_url": "https://www.wireguard.com/",
    },
]


@patch("app.routers.registry.httpx")
def test_list_registry_images(mock_httpx, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = client.get("/api/registry/images")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "firefox"
    assert data[0]["project_logo"] is not None


@patch("app.routers.registry.httpx")
def test_list_registry_filter_category(mock_httpx, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = client.get("/api/registry/images?category=Network")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "wireguard"


@patch("app.routers.registry.httpx")
def test_list_registry_search(mock_httpx, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = client.get("/api/registry/images?search=fire")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "firefox"


@patch("app.routers.registry.httpx")
def test_get_registry_image(mock_httpx, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = client.get("/api/registry/images/firefox")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "firefox"
    assert "config" in data


@patch("app.routers.registry.httpx")
def test_get_registry_image_not_found(mock_httpx, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = client.get("/api/registry/images/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Add httpx to dependencies**

In `backend/pyproject.toml`, add `"httpx>=0.28.0"` to `dependencies` list (it's already in dev deps but needed at runtime now).

- [ ] **Step 4: Implement registry proxy**

```python
# backend/app/routers/registry.py
import time

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

LSIO_API_URL = "https://api.linuxserver.io/api/v1/images?include_config=true&include_deprecated=false"
_cache: dict = {"data": None, "fetched_at": 0}
CACHE_TTL = 3600


def _fetch_images() -> list[dict]:
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["data"]

    resp = httpx.get(LSIO_API_URL, timeout=30)
    resp.raise_for_status()
    _cache["data"] = resp.json()
    _cache["fetched_at"] = now
    return _cache["data"]


@router.get("")
def list_images(
    category: str | None = Query(None),
    search: str | None = Query(None),
):
    try:
        images = _fetch_images()
    except httpx.HTTPError:
        raise HTTPException(502, "Failed to fetch LinuxServer registry")

    if category:
        images = [
            img for img in images
            if category.lower() in (img.get("category") or "").lower()
        ]
    if search:
        q = search.lower()
        images = [
            img for img in images
            if q in (img.get("name") or "").lower()
            or q in (img.get("description") or "").lower()
        ]

    return images


@router.get("/{name}")
def get_image(name: str):
    try:
        images = _fetch_images()
    except httpx.HTTPError:
        raise HTTPException(502, "Failed to fetch LinuxServer registry")

    for img in images:
        if img["name"] == name:
            return img
    raise HTTPException(404, f"Image '{name}' not found")
```

- [ ] **Step 5: Register router in main.py**

Add to `backend/app/main.py`, after existing router imports:

```python
from app.routers import templates, instances, registry
```

And after existing `app.include_router` lines:

```python
app.include_router(registry.router, prefix="/api/registry/images", tags=["registry"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_registry.py -v`
Expected: 5 passed

- [ ] **Step 7: Run full backend test suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: All 49+ tests pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/registry.py backend/tests/test_registry.py backend/app/main.py backend/pyproject.toml
git commit -m "feat: LinuxServer registry proxy with caching"
```

---

## Task 2: Backend — Screenshot Service

**Files:**
- Create: `backend/app/services/screenshot.py`
- Create: `backend/tests/test_screenshots.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/routers/instances.py`

- [ ] **Step 1: Write screenshot service tests**

```python
# backend/tests/test_screenshots.py
import tempfile
from unittest.mock import MagicMock, patch
from pathlib import Path

from app.services.screenshot import ScreenshotService


def test_screenshot_cache_dir_created():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
        assert Path(tmpdir).is_dir()


@patch("app.services.screenshot.httpx")
def test_capture_screenshot(mock_httpx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"\x89PNG fake image data"
    mock_httpx.get.return_value = mock_response

    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "selkies-hub": {"IPAddress": "172.18.0.5"}
            }
        }
    }
    mock_docker._client.containers.get.return_value = mock_container

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=mock_docker)
        result = svc.capture("instance-123", "container-abc", 3001)

        assert result is True
        cached = Path(tmpdir) / "instance-123.png"
        assert cached.exists()
        assert cached.read_bytes() == b"\x89PNG fake image data"


@patch("app.services.screenshot.httpx")
def test_capture_screenshot_failure(mock_httpx):
    mock_httpx.get.side_effect = Exception("connection refused")
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "selkies-hub": {"IPAddress": "172.18.0.5"}
            }
        }
    }
    mock_docker._client.containers.get.return_value = mock_container

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=mock_docker)
        result = svc.capture("inst-1", "cont-1", 3001)
        assert result is False


def test_get_screenshot_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())

        assert svc.get_path("nonexistent") is None

        cached = Path(tmpdir) / "inst-1.png"
        cached.write_bytes(b"\x89PNG data")
        assert svc.get_path("inst-1") == cached
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_screenshots.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement screenshot service**

```python
# backend/app/services/screenshot.py
from pathlib import Path

import httpx

from app.services.docker_manager import DockerManager


class ScreenshotService:
    def __init__(self, cache_dir: str, docker_manager: DockerManager):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._docker = docker_manager

    def capture(self, instance_id: str, container_id: str, port: int) -> bool:
        try:
            container = self._docker._client.containers.get(container_id)
            networks = container.attrs["NetworkSettings"]["Networks"]
            ip = None
            for net in networks.values():
                ip = net.get("IPAddress")
                if ip:
                    break
            if not ip:
                return False

            resp = httpx.get(f"http://{ip}:{port}/screenshot", timeout=10)
            if resp.status_code != 200:
                return False

            path = self._cache_dir / f"{instance_id}.png"
            path.write_bytes(resp.content)
            return True
        except Exception:
            return False

    def get_path(self, instance_id: str) -> Path | None:
        path = self._cache_dir / f"{instance_id}.png"
        if path.exists():
            return path
        return None
```

- [ ] **Step 4: Add SCREENSHOT_CACHE_DIR to config**

Add to `backend/app/config.py` Settings class:

```python
SCREENSHOT_CACHE_DIR: str = "/app/data/screenshots"
```

- [ ] **Step 5: Add screenshot endpoint to instances router**

Add these imports to the top of `backend/app/routers/instances.py`:

```python
from fastapi.responses import FileResponse
from app.services.screenshot import ScreenshotService
```

Add this dependency function after `get_docker_manager()`:

```python
def get_screenshot_service() -> ScreenshotService:
    return ScreenshotService(
        cache_dir=_settings.SCREENSHOT_CACHE_DIR,
        docker_manager=get_docker_manager(),
    )
```

Add this endpoint at the bottom of the file:

```python
@router.get("/{instance_id}/screenshot")
def get_screenshot(
    instance_id: str,
    session: Session = Depends(get_session),
    screenshots: ScreenshotService = Depends(get_screenshot_service),
):
    instance = session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    path = screenshots.get_path(instance_id)
    if not path:
        raise HTTPException(404, "No screenshot available")

    return FileResponse(path, media_type="image/png")
```

- [ ] **Step 6: Wire screenshot capture into session monitor loop**

Replace `_session_monitor_loop` in `backend/app/main.py`:

```python
from app.services.screenshot import ScreenshotService

async def _session_monitor_loop():
    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    monitor = SessionMonitor(docker)
    screenshots = ScreenshotService(
        cache_dir=_settings.SCREENSHOT_CACHE_DIR, docker_manager=docker
    )
    tick = 0
    while True:
        await asyncio.sleep(10)
        tick += 1
        try:
            with Session(engine) as session:
                if tick % 6 == 0:
                    monitor.check_all(session)
                if tick % 3 == 0:
                    from sqlmodel import select
                    from app.models import Instance as InstanceModel
                    running = session.exec(
                        select(InstanceModel).where(
                            InstanceModel.status.in_(["running", "idle"])
                        )
                    ).all()
                    for inst in running:
                        if inst.container_id:
                            screenshots.capture(inst.id, inst.container_id, 3001)
        except Exception:
            pass
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_screenshots.py -v`
Expected: 4 passed

- [ ] **Step 8: Run full backend test suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/screenshot.py backend/tests/test_screenshots.py \
        backend/app/routers/instances.py backend/app/main.py backend/app/config.py
git commit -m "feat: screenshot capture service and endpoint"
```

---

## Task 3: Backend — CORS Middleware

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add CORS middleware for frontend dev server**

Add to `backend/app/main.py`, after `app = FastAPI(...)`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", f"https://{_settings.DOMAIN}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: Run full test suite to verify nothing broke**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: CORS middleware for frontend dev server"
```

---

## Task 4: Frontend — Project Scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.app.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/src/vite-env.d.ts`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "selkies-hub-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^19.1.0",
    "react-dom": "^19.1.0",
    "react-router": "^7.6.1",
    "@tanstack/react-query": "^5.75.5",
    "lucide-react": "^0.511.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.3.0",
    "class-variance-authority": "^0.7.1",
    "sonner": "^2.0.3"
  },
  "devDependencies": {
    "@types/react": "^19.1.4",
    "@types/react-dom": "^19.1.5",
    "@vitejs/plugin-react": "^4.5.2",
    "typescript": "~5.8.3",
    "vite": "^6.3.5",
    "tailwindcss": "^4.1.7",
    "@tailwindcss/vite": "^4.1.7"
  }
}
```

- [ ] **Step 2: Create vite.config.ts**

```typescript
// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
```

- [ ] **Step 3: Create tsconfig files**

```json
// frontend/tsconfig.json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

```json
// frontend/tsconfig.app.json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"]
}
```

```json
// frontend/tsconfig.node.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create postcss.config.js**

```javascript
// frontend/postcss.config.js
export default {};
```

- [ ] **Step 5: Create index.html**

```html
<!-- frontend/index.html -->
<!DOCTYPE html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Selkies Hub</title>
  </head>
  <body class="min-h-screen bg-background text-foreground antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create globals.css with Tailwind + theme vars**

```css
/* frontend/src/styles/globals.css */
@import "tailwindcss";

@theme inline {
  --color-background: oklch(0.145 0 0);
  --color-foreground: oklch(0.985 0 0);
  --color-card: oklch(0.178 0.005 265);
  --color-card-foreground: oklch(0.985 0 0);
  --color-popover: oklch(0.178 0.005 265);
  --color-popover-foreground: oklch(0.985 0 0);
  --color-primary: oklch(0.61 0.17 255);
  --color-primary-foreground: oklch(0.985 0 0);
  --color-secondary: oklch(0.269 0.006 265);
  --color-secondary-foreground: oklch(0.985 0 0);
  --color-muted: oklch(0.269 0.006 265);
  --color-muted-foreground: oklch(0.708 0.015 265);
  --color-accent: oklch(0.269 0.006 265);
  --color-accent-foreground: oklch(0.985 0 0);
  --color-destructive: oklch(0.577 0.245 27.325);
  --color-border: oklch(0.353 0.013 265);
  --color-input: oklch(0.353 0.013 265);
  --color-ring: oklch(0.61 0.17 255);
  --color-success: oklch(0.696 0.17 162.48);
  --color-warning: oklch(0.795 0.184 86.047);
  --color-idle: oklch(0.795 0.184 86.047);
  --radius: 0.625rem;
}
```

- [ ] **Step 7: Create vite-env.d.ts**

```typescript
// frontend/src/vite-env.d.ts
/// <reference types="vite/client" />
```

- [ ] **Step 8: Create main.tsx**

```tsx
// frontend/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import App from "./App";
import "./styles/globals.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster theme="dark" />
    </QueryClientProvider>
  </StrictMode>
);
```

- [ ] **Step 9: Create placeholder App.tsx**

```tsx
// frontend/src/App.tsx
export default function App() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <h1 className="text-2xl font-bold text-primary">Selkies Hub</h1>
    </div>
  );
}
```

- [ ] **Step 10: Install dependencies and verify dev server starts**

```bash
cd frontend && npm install
npm run dev -- --host 0.0.0.0
```

Open `http://localhost:5173` — should see "Selkies Hub" centered on dark background.

- [ ] **Step 11: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 12: Commit**

```bash
git add frontend/
git commit -m "feat: frontend project scaffolding with Vite, React, Tailwind"
```

---

## Task 5: Frontend — Types, Utils, API Client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Create TypeScript types matching backend API**

```typescript
// frontend/src/lib/types.ts
export interface SessionConfig {
  idle_timeout: string;
  grace_period: string;
  timeout_action: "stop" | "destroy";
  never_timeout: boolean;
  max_session_duration: string | null;
}

export interface ServiceTemplate {
  id: string;
  name: string;
  display_name: string;
  image: string;
  icon: string | null;
  description: string | null;
  env_vars: Record<string, string>;
  gpu_enabled: boolean;
  gpu_count: number;
  memory_limit: string | null;
  cpu_limit: string | null;
  shm_size: string | null;
  volumes: { name: string; mount: string }[];
  internal_port: number;
  category: string | null;
  tags: string[];
  session_config: SessionConfig;
  created_at: string;
  updated_at: string;
}

export interface Instance {
  id: string;
  template_id: string;
  name: string;
  subdomain: string;
  container_id: string | null;
  status: "created" | "creating" | "starting" | "running" | "idle" | "stopping" | "stopped" | "error";
  env_overrides: Record<string, string>;
  volume_names: string[];
  created_at: string;
  started_at: string | null;
  stopped_at: string | null;
  last_activity: string | null;
  session_config: SessionConfig | null;
}

export interface InstanceStatus {
  id: string;
  status: string;
  container_id: string | null;
  uptime_seconds: number | null;
  idle_seconds: number | null;
  session_config: SessionConfig | null;
}

export interface RegistryImage {
  name: string;
  description: string;
  project_logo: string;
  category: string;
  stars: number;
  monthly_pulls: number;
  version: string;
  stable: boolean;
  config: {
    env_vars: { name: string; default: string; description: string }[];
    volumes: { container: string; description: string }[];
    ports: { container: string; description: string }[];
  };
  architectures: { arch: string; tag: string }[];
  github_url: string;
  project_url: string;
}

export interface InstanceCreate {
  template_id: string;
  name: string;
  subdomain: string;
  env_overrides?: Record<string, string>;
  session_config?: Partial<SessionConfig>;
}

export interface TemplateCreate {
  name: string;
  display_name: string;
  image: string;
  icon?: string;
  description?: string;
  env_vars?: Record<string, string>;
  gpu_enabled?: boolean;
  gpu_count?: number;
  memory_limit?: string;
  cpu_limit?: string;
  shm_size?: string;
  volumes?: { name: string; mount: string }[];
  internal_port?: number;
  category?: string;
  tags?: string[];
  session_config?: Partial<SessionConfig>;
}
```

- [ ] **Step 2: Create utils**

```typescript
// frontend/src/lib/utils.ts
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "—";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}
```

- [ ] **Step 3: Create API client**

```typescript
// frontend/src/api/client.ts
import type {
  Instance,
  InstanceCreate,
  InstanceStatus,
  RegistryImage,
  ServiceTemplate,
  TemplateCreate,
} from "@/lib/types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  listInstances: () => request<Instance[]>("/instances"),
  createInstance: (data: InstanceCreate) =>
    request<Instance>("/instances", { method: "POST", body: JSON.stringify(data) }),
  startInstance: (id: string) =>
    request<Instance>(`/instances/${id}/start`, { method: "POST" }),
  stopInstance: (id: string) =>
    request<Instance>(`/instances/${id}/stop`, { method: "POST" }),
  deleteInstance: (id: string, removeVolumes = false) =>
    request<void>(`/instances/${id}?remove_volumes=${removeVolumes}`, { method: "DELETE" }),
  getInstanceStatus: (id: string) =>
    request<InstanceStatus>(`/instances/${id}/status`),
  keepalive: (id: string) =>
    request<Instance>(`/instances/${id}/keepalive`, { method: "POST" }),
  screenshotUrl: (id: string) => `${BASE}/instances/${id}/screenshot`,

  listTemplates: () => request<ServiceTemplate[]>("/templates"),
  createTemplate: (data: TemplateCreate) =>
    request<ServiceTemplate>("/templates", { method: "POST", body: JSON.stringify(data) }),
  deleteTemplate: (id: string) => request<void>(`/templates/${id}`, { method: "DELETE" }),

  listRegistryImages: (params?: { category?: string; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set("category", params.category);
    if (params?.search) qs.set("search", params.search);
    const q = qs.toString();
    return request<RegistryImage[]>(`/registry/images${q ? `?${q}` : ""}`);
  },
  getRegistryImage: (name: string) => request<RegistryImage>(`/registry/images/${name}`),
};
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/ frontend/src/api/
git commit -m "feat: TypeScript types, utils, and API client"
```

---

## Task 6: Frontend — TanStack Query Hooks

**Files:**
- Create: `frontend/src/hooks/use-instances.ts`
- Create: `frontend/src/hooks/use-templates.ts`
- Create: `frontend/src/hooks/use-registry.ts`

- [ ] **Step 1: Create instances hook**

```typescript
// frontend/src/hooks/use-instances.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { InstanceCreate } from "@/lib/types";

export function useInstances() {
  return useQuery({
    queryKey: ["instances"],
    queryFn: api.listInstances,
    refetchInterval: 5000,
  });
}

export function useCreateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: InstanceCreate) => api.createInstance(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useStartInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.startInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useStopInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.stopInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}

export function useDeleteInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, removeVolumes }: { id: string; removeVolumes: boolean }) =>
      api.deleteInstance(id, removeVolumes),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}
```

- [ ] **Step 2: Create templates hook**

```typescript
// frontend/src/hooks/use-templates.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { TemplateCreate } from "@/lib/types";

export function useTemplates() {
  return useQuery({
    queryKey: ["templates"],
    queryFn: api.listTemplates,
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TemplateCreate) => api.createTemplate(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteTemplate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
}
```

- [ ] **Step 3: Create registry hook**

```typescript
// frontend/src/hooks/use-registry.ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function useRegistryImages(params?: { category?: string; search?: string }) {
  return useQuery({
    queryKey: ["registry", params?.category, params?.search],
    queryFn: () => api.listRegistryImages(params),
    staleTime: 60 * 60 * 1000,
  });
}

export function useRegistryImage(name: string) {
  return useQuery({
    queryKey: ["registry", name],
    queryFn: () => api.getRegistryImage(name),
    enabled: !!name,
  });
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/
git commit -m "feat: TanStack Query hooks for instances, templates, registry"
```

---

## Task 7: Frontend — shadcn/ui Components

**Files:**
- Create: `frontend/components.json`
- Create: multiple files in `frontend/src/components/ui/`

- [ ] **Step 1: Create components.json for shadcn**

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/globals.css",
    "baseColor": "zinc",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

- [ ] **Step 2: Install shadcn components**

```bash
cd frontend
npx shadcn@latest add button card dialog badge input tabs dropdown-menu separator label switch select textarea -y
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/components.json frontend/src/components/ui/
git commit -m "feat: shadcn/ui components (button, card, dialog, badge, etc.)"
```

---

## Task 8: Frontend — Layout Components (Header + Tab Nav)

**Files:**
- Create: `frontend/src/components/layout/header.tsx`
- Create: `frontend/src/components/layout/tab-nav.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create header component**

```tsx
// frontend/src/components/layout/header.tsx
import { Monitor, Moon, Sun } from "lucide-react";
import { useInstances } from "@/hooks/use-instances";
import { useEffect, useState } from "react";

function ThemeToggle() {
  const [dark, setDark] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "light") {
      setDark(false);
      document.documentElement.classList.remove("dark");
    } else if (stored === "dark" || !stored) {
      setDark(true);
      document.documentElement.classList.add("dark");
    }
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  }

  return (
    <button onClick={toggle} className="rounded-md p-2 hover:bg-secondary">
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

export function Header() {
  const { data: instances } = useInstances();
  const running = instances?.filter((i) => i.status === "running" || i.status === "idle").length ?? 0;
  const stopped = instances?.filter((i) => i.status === "stopped").length ?? 0;

  return (
    <header className="flex items-center gap-4 border-b border-border px-6 py-3">
      <Monitor className="h-5 w-5 text-primary" />
      <span className="text-lg font-bold">Selkies Hub</span>
      <span className="ml-auto text-sm text-muted-foreground">
        {running > 0 && <span className="text-success">{running} running</span>}
        {running > 0 && stopped > 0 && <span> · </span>}
        {stopped > 0 && <span>{stopped} stopped</span>}
      </span>
      <ThemeToggle />
    </header>
  );
}
```

- [ ] **Step 2: Create tab nav component**

```tsx
// frontend/src/components/layout/tab-nav.tsx
import { cn } from "@/lib/utils";

interface TabNavProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const TABS = [
  { id: "instances", label: "My Instances" },
  { id: "templates", label: "Template Gallery" },
];

export function TabNav({ activeTab, onTabChange }: TabNavProps) {
  return (
    <div className="flex gap-1 border-b border-border px-6">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={cn(
            "px-4 py-2.5 text-sm font-medium transition-colors",
            "hover:text-foreground",
            activeTab === tab.id
              ? "border-b-2 border-primary text-foreground"
              : "text-muted-foreground"
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Wire layout into App.tsx**

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";

export default function App() {
  const [activeTab, setActiveTab] = useState("instances");

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        {activeTab === "instances" && (
          <p className="text-muted-foreground">Instances tab — coming next</p>
        )}
        {activeTab === "templates" && (
          <p className="text-muted-foreground">Templates tab — coming next</p>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles and dev server renders**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/ frontend/src/App.tsx
git commit -m "feat: layout — header with theme toggle and tab navigation"
```

---

## Task 9: Frontend — Instance Cards and Grid

**Files:**
- Create: `frontend/src/components/instances/status-badge.tsx`
- Create: `frontend/src/components/instances/instance-card.tsx`
- Create: `frontend/src/components/instances/instance-grid.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create status badge**

```tsx
// frontend/src/components/instances/status-badge.tsx
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<string, { dot: string; text: string }> = {
  running: { dot: "bg-success", text: "text-success" },
  idle: { dot: "bg-warning", text: "text-warning" },
  stopped: { dot: "bg-muted-foreground", text: "text-muted-foreground" },
  error: { dot: "bg-destructive", text: "text-destructive" },
  creating: { dot: "bg-primary", text: "text-primary" },
  starting: { dot: "bg-primary", text: "text-primary" },
  stopping: { dot: "bg-warning", text: "text-warning" },
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.stopped;
  return (
    <span className={cn("flex items-center gap-1.5 text-xs font-medium", style.text)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
```

- [ ] **Step 2: Create instance card**

```tsx
// frontend/src/components/instances/instance-card.tsx
import { MoreHorizontal, ExternalLink, Play, Square, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusBadge } from "./status-badge";
import { api } from "@/api/client";
import { formatDuration } from "@/lib/utils";
import { useStartInstance, useStopInstance, useDeleteInstance } from "@/hooks/use-instances";
import { toast } from "sonner";
import type { Instance } from "@/lib/types";
import { useState } from "react";

interface InstanceCardProps {
  instance: Instance;
  domain: string;
  onSelect: (instance: Instance) => void;
}

export function InstanceCard({ instance, domain, onSelect }: InstanceCardProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const destroy = useDeleteInstance();
  const [imgError, setImgError] = useState(false);

  const isRunning = instance.status === "running" || instance.status === "idle";
  const idleSeconds = instance.last_activity
    ? (Date.now() - new Date(instance.last_activity).getTime()) / 1000
    : null;

  function handleConnect() {
    window.open(`https://${instance.subdomain}.${domain}`, "_blank");
  }

  function handleStart() {
    start.mutate(instance.id, {
      onError: (e) => toast.error(`Start failed: ${e.message}`),
    });
  }

  function handleStop() {
    stop.mutate(instance.id, {
      onError: (e) => toast.error(`Stop failed: ${e.message}`),
    });
  }

  function handleDestroy() {
    if (!confirm(`Destroy "${instance.name}"? This removes the container.`)) return;
    destroy.mutate(
      { id: instance.id, removeVolumes: false },
      { onError: (e) => toast.error(`Destroy failed: ${e.message}`) }
    );
  }

  return (
    <div
      className="group cursor-pointer overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/50"
      onClick={() => onSelect(instance)}
    >
      <div className="relative aspect-video w-full bg-secondary">
        {isRunning && !imgError ? (
          <img
            src={`${api.screenshotUrl(instance.id)}?t=${Math.floor(Date.now() / 30000)}`}
            alt={instance.name}
            className="h-full w-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-4xl text-muted-foreground/30">
            {instance.status === "stopped" ? "⏸" : "🖥️"}
          </div>
        )}
      </div>

      <div className="p-4">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="flex-1 truncate font-semibold">{instance.name}</h3>
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" size="icon" className="h-7 w-7">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {isRunning && (
                <DropdownMenuItem onClick={handleStop}>
                  <Square className="mr-2 h-3 w-3" /> Stop
                </DropdownMenuItem>
              )}
              {!isRunning && (
                <DropdownMenuItem onClick={handleStart}>
                  <Play className="mr-2 h-3 w-3" /> Start
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={handleDestroy} className="text-destructive">
                <Trash2 className="mr-2 h-3 w-3" /> Destroy
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="mb-3 flex items-center gap-3">
          <StatusBadge status={instance.status} />
          {isRunning && idleSeconds != null && (
            <span className="text-xs text-muted-foreground">
              {formatDuration(idleSeconds)} idle
            </span>
          )}
        </div>

        {isRunning ? (
          <Button size="sm" className="w-full" onClick={(e) => { e.stopPropagation(); handleConnect(); }}>
            <ExternalLink className="mr-2 h-3 w-3" /> Connect
          </Button>
        ) : (
          <Button size="sm" variant="secondary" className="w-full" onClick={(e) => { e.stopPropagation(); handleStart(); }}>
            <Play className="mr-2 h-3 w-3" /> Start
          </Button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create instance grid**

```tsx
// frontend/src/components/instances/instance-grid.tsx
import { useInstances } from "@/hooks/use-instances";
import { InstanceCard } from "./instance-card";
import type { Instance } from "@/lib/types";

interface InstanceGridProps {
  onSelect: (instance: Instance) => void;
  onLaunch: () => void;
}

export function InstanceGrid({ onSelect, onLaunch }: InstanceGridProps) {
  const { data: instances, isLoading, isError } = useInstances();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="aspect-[4/3] animate-pulse rounded-xl bg-card" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-center text-sm text-destructive">
        Backend unavailable — retrying...
      </div>
    );
  }

  if (!instances?.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <p className="mb-1 text-lg font-medium text-foreground">No instances yet</p>
        <p className="mb-4 text-sm text-muted-foreground">
          Browse the Template Gallery to launch one.
        </p>
        <button onClick={onLaunch} className="text-sm font-medium text-primary hover:underline">
          Go to Template Gallery &rarr;
        </button>
      </div>
    );
  }

  const domain = window.location.hostname === "localhost"
    ? "localhost"
    : window.location.hostname.split(".").slice(1).join(".");

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {instances.map((instance) => (
        <InstanceCard key={instance.id} instance={instance} domain={domain} onSelect={onSelect} />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Update App.tsx to render instance grid**

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";
import { InstanceGrid } from "@/components/instances/instance-grid";
import type { Instance } from "@/lib/types";

export default function App() {
  const [activeTab, setActiveTab] = useState("instances");
  const [_selectedInstance, setSelectedInstance] = useState<Instance | null>(null);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        {activeTab === "instances" && (
          <InstanceGrid onSelect={setSelectedInstance} onLaunch={() => setActiveTab("templates")} />
        )}
        {activeTab === "templates" && (
          <p className="text-muted-foreground">Templates tab — coming next</p>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/instances/ frontend/src/App.tsx
git commit -m "feat: instance cards with screenshots, status badges, and responsive grid"
```

---

## Task 10: Frontend — Template Gallery + Registry Browser

**Files:**
- Create: `frontend/src/components/templates/template-card.tsx`
- Create: `frontend/src/components/templates/template-grid.tsx`
- Create: `frontend/src/components/templates/registry-browser.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create template card**

```tsx
// frontend/src/components/templates/template-card.tsx
import { Trash2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useDeleteTemplate } from "@/hooks/use-templates";
import { toast } from "sonner";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateCardProps {
  template: ServiceTemplate;
  onLaunch: (template: ServiceTemplate) => void;
}

export function TemplateCard({ template, onLaunch }: TemplateCardProps) {
  const deleteTemplate = useDeleteTemplate();

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Delete template "${template.display_name}"?`)) return;
    deleteTemplate.mutate(template.id, {
      onError: (err) => toast.error(`Delete failed: ${err.message}`),
    });
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/50">
      <div className="mb-3 flex items-start gap-3">
        <span className="text-2xl">{template.icon ?? "📦"}</span>
        <div className="flex-1">
          <h3 className="font-semibold">{template.display_name}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{template.description}</p>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap gap-1">
        {template.category && <Badge variant="secondary" className="text-[10px]">{template.category}</Badge>}
        {template.gpu_enabled && <Badge variant="secondary" className="text-[10px]">GPU</Badge>}
        {template.memory_limit && <Badge variant="outline" className="text-[10px]">{template.memory_limit} RAM</Badge>}
      </div>
      <div className="flex gap-2">
        <Button size="sm" className="flex-1" onClick={() => onLaunch(template)}>
          <Play className="mr-1.5 h-3 w-3" /> Launch
        </Button>
        <Button size="sm" variant="ghost" onClick={handleDelete}>
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create registry browser**

```tsx
// frontend/src/components/templates/registry-browser.tsx
import { useState } from "react";
import { Search, Star, Download } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRegistryImages } from "@/hooks/use-registry";
import type { RegistryImage } from "@/lib/types";

interface RegistryBrowserProps {
  onImport: (image: RegistryImage) => void;
}

const CATEGORIES = ["All", "Productivity", "Network", "Media", "Tools", "DNS", "Web", "Gaming"];

export function RegistryBrowser({ onImport }: RegistryBrowserProps) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const { data: images, isLoading, isError } = useRegistryImages({
    category: category === "All" ? undefined : category,
    search: search || undefined,
  });

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search images..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
        <div className="flex gap-1 flex-wrap">
          {CATEGORIES.map((cat) => (
            <Button key={cat} variant={category === cat ? "default" : "ghost"} size="sm" onClick={() => setCategory(cat)} className="text-xs">
              {cat}
            </Button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-card" />)}
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-center text-sm text-destructive">
          Could not load LinuxServer registry.
        </div>
      )}

      {images && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {images.map((img) => (
            <div key={img.name} className="flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-3 transition-colors hover:border-primary/50" onClick={() => onImport(img)}>
              <img src={img.project_logo} alt={img.name} className="h-10 w-10 rounded-md object-contain" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
              <div className="flex-1 overflow-hidden">
                <h4 className="truncate text-sm font-semibold">{img.name}</h4>
                <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{img.description}</p>
                <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
                  <span className="flex items-center gap-1"><Star className="h-3 w-3" /> {img.stars}</span>
                  <span className="flex items-center gap-1"><Download className="h-3 w-3" /> {(img.monthly_pulls / 1000).toFixed(0)}k/mo</span>
                  {img.category && <Badge variant="outline" className="text-[10px] px-1 py-0">{img.category}</Badge>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {images && images.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">No images match your search.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create template grid**

```tsx
// frontend/src/components/templates/template-grid.tsx
import { useTemplates } from "@/hooks/use-templates";
import { TemplateCard } from "./template-card";
import type { ServiceTemplate } from "@/lib/types";

interface TemplateGridProps {
  onLaunch: (template: ServiceTemplate) => void;
}

export function TemplateGrid({ onLaunch }: TemplateGridProps) {
  const { data: templates, isLoading } = useTemplates();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => <div key={i} className="h-40 animate-pulse rounded-xl bg-card" />)}
      </div>
    );
  }

  if (!templates?.length) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No saved templates. Import one from the LinuxServer Registry.</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {templates.map((t) => <TemplateCard key={t.id} template={t} onLaunch={onLaunch} />)}
    </div>
  );
}
```

- [ ] **Step 4: Update App.tsx with template gallery**

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";
import { InstanceGrid } from "@/components/instances/instance-grid";
import { TemplateGrid } from "@/components/templates/template-grid";
import { RegistryBrowser } from "@/components/templates/registry-browser";
import { cn } from "@/lib/utils";
import type { Instance, ServiceTemplate, RegistryImage } from "@/lib/types";

export default function App() {
  const [activeTab, setActiveTab] = useState("instances");
  const [templateSubTab, setTemplateSubTab] = useState("registry");
  const [_selectedInstance, setSelectedInstance] = useState<Instance | null>(null);
  const [_launchRegistry, setLaunchRegistry] = useState<RegistryImage | null>(null);
  const [_launchTemplate, setLaunchTemplate] = useState<ServiceTemplate | null>(null);

  function handleImportRegistry(image: RegistryImage) {
    setLaunchRegistry(image);
    setLaunchTemplate(null);
  }

  function handleLaunchTemplate(template: ServiceTemplate) {
    setLaunchTemplate(template);
    setLaunchRegistry(null);
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        {activeTab === "instances" && (
          <InstanceGrid onSelect={setSelectedInstance} onLaunch={() => setActiveTab("templates")} />
        )}
        {activeTab === "templates" && (
          <div>
            <div className="mb-4 flex gap-1">
              {[
                { id: "registry", label: "LinuxServer Registry" },
                { id: "my-templates", label: "My Templates" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setTemplateSubTab(tab.id)}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                    templateSubTab === tab.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            {templateSubTab === "registry" && <RegistryBrowser onImport={handleImportRegistry} />}
            {templateSubTab === "my-templates" && <TemplateGrid onLaunch={handleLaunchTemplate} />}
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/templates/ frontend/src/App.tsx
git commit -m "feat: template gallery with LinuxServer registry browser"
```

---

## Task 11: Frontend — Launch Modal with Env Editor

**Files:**
- Create: `frontend/src/components/templates/env-editor.tsx`
- Create: `frontend/src/components/templates/launch-modal.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create env editor component**

```tsx
// frontend/src/components/templates/env-editor.tsx
import { Plus, Trash2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface EnvEditorProps {
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  descriptions?: Record<string, string>;
}

export function EnvEditor({ value, onChange, descriptions }: EnvEditorProps) {
  const entries = Object.entries(value);

  function update(oldKey: string, newKey: string, newVal: string) {
    const next = { ...value };
    if (oldKey !== newKey) delete next[oldKey];
    next[newKey] = newVal;
    onChange(next);
  }

  function remove(key: string) {
    const next = { ...value };
    delete next[key];
    onChange(next);
  }

  function add() {
    onChange({ ...value, "": "" });
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, val], i) => (
        <div key={i} className="flex items-start gap-2">
          <div className="flex-1">
            <Input value={key} onChange={(e) => update(key, e.target.value, val)} placeholder="KEY" className="font-mono text-xs" />
            {descriptions?.[key] && <p className="mt-0.5 text-[10px] text-muted-foreground">{descriptions[key]}</p>}
          </div>
          <Input value={val} onChange={(e) => update(key, key, e.target.value)} placeholder="value" className="flex-1 font-mono text-xs" />
          <Button variant="ghost" size="icon" className="h-9 w-9" onClick={() => remove(key)}>
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={add}>
        <Plus className="mr-1.5 h-3 w-3" /> Add Variable
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Create launch modal**

```tsx
// frontend/src/components/templates/launch-modal.tsx
import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { EnvEditor } from "./env-editor";
import { useCreateTemplate } from "@/hooks/use-templates";
import { useCreateInstance } from "@/hooks/use-instances";
import { slugify } from "@/lib/utils";
import { toast } from "sonner";
import type { RegistryImage, ServiceTemplate } from "@/lib/types";

interface LaunchModalProps {
  open: boolean;
  onClose: () => void;
  registryImage?: RegistryImage | null;
  template?: ServiceTemplate | null;
}

export function LaunchModal({ open, onClose, registryImage, template }: LaunchModalProps) {
  const createTemplate = useCreateTemplate();
  const createInstance = useCreateInstance();

  const prefillName = registryImage?.name ?? template?.display_name ?? "";
  const prefillImage = registryImage ? `lscr.io/linuxserver/${registryImage.name}:latest` : template?.image ?? "";

  const prefillEnv: Record<string, string> = {};
  const envDescriptions: Record<string, string> = {};
  if (registryImage?.config?.env_vars) {
    for (const v of registryImage.config.env_vars) {
      prefillEnv[v.name] = v.default ?? "";
      envDescriptions[v.name] = v.description ?? "";
    }
  } else if (template?.env_vars) {
    Object.assign(prefillEnv, template.env_vars);
  }

  const prefillVolumes: { name: string; mount: string }[] = [];
  if (registryImage?.config?.volumes) {
    for (const v of registryImage.config.volumes) {
      prefillVolumes.push({ name: `{instance_id}${v.container.replace(/\//g, "-")}`, mount: v.container });
    }
  } else if (template?.volumes) {
    prefillVolumes.push(...template.volumes);
  }

  const [name, setName] = useState(prefillName);
  const [subdomain, setSubdomain] = useState(slugify(prefillName));
  const [image, setImage] = useState(prefillImage);
  const [memoryLimit, setMemoryLimit] = useState(template?.memory_limit ?? "4g");
  const [cpuLimit, setCpuLimit] = useState(template?.cpu_limit ?? "2.0");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [envVars, setEnvVars] = useState(prefillEnv);
  const [gpuEnabled, setGpuEnabled] = useState(template?.gpu_enabled ?? false);
  const [gpuCount, setGpuCount] = useState(template?.gpu_count ?? 1);
  const [shmSize, setShmSize] = useState(template?.shm_size ?? "1g");
  const [volumes, setVolumes] = useState(prefillVolumes);
  const [idleTimeout, setIdleTimeout] = useState("30m");
  const [gracePeriod, setGracePeriod] = useState("5m");

  async function handleSaveAndLaunch() {
    try {
      const tmpl = await createTemplate.mutateAsync({
        name: slugify(name),
        display_name: name,
        image,
        description: registryImage?.description ?? template?.description ?? "",
        env_vars: envVars,
        gpu_enabled: gpuEnabled,
        gpu_count: gpuEnabled ? gpuCount : 0,
        memory_limit: memoryLimit,
        cpu_limit: cpuLimit,
        shm_size: shmSize,
        volumes,
        internal_port: 3001,
        category: registryImage?.category ?? template?.category ?? undefined,
        tags: [],
        session_config: { idle_timeout: idleTimeout, grace_period: gracePeriod, timeout_action: "stop", never_timeout: false, max_session_duration: null },
      });
      await createInstance.mutateAsync({ template_id: tmpl.id, name, subdomain });
      toast.success(`Instance "${name}" launched!`);
      onClose();
    } catch (e) {
      toast.error(`Launch failed: ${(e as Error).message}`);
    }
  }

  async function handleSaveTemplate() {
    try {
      await createTemplate.mutateAsync({
        name: slugify(name),
        display_name: name,
        image,
        description: registryImage?.description ?? template?.description ?? "",
        env_vars: envVars,
        gpu_enabled: gpuEnabled,
        gpu_count: gpuEnabled ? gpuCount : 0,
        memory_limit: memoryLimit,
        cpu_limit: cpuLimit,
        shm_size: shmSize,
        volumes,
        internal_port: 3001,
        category: registryImage?.category ?? template?.category ?? undefined,
        tags: [],
        session_config: { idle_timeout: idleTimeout, grace_period: gracePeriod, timeout_action: "stop", never_timeout: false, max_session_duration: null },
      });
      toast.success(`Template "${name}" saved!`);
      onClose();
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {registryImage ? `Import: ${registryImage.name}` : template ? `Launch: ${template.display_name}` : "Custom Template"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Name</Label><Input value={name} onChange={(e) => { setName(e.target.value); setSubdomain(slugify(e.target.value)); }} /></div>
            <div><Label>Subdomain</Label><Input value={subdomain} onChange={(e) => setSubdomain(e.target.value)} className="font-mono text-sm" /></div>
          </div>
          <div><Label>Docker Image</Label><Input value={image} onChange={(e) => setImage(e.target.value)} className="font-mono text-sm" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Memory Limit</Label><Input value={memoryLimit} onChange={(e) => setMemoryLimit(e.target.value)} /></div>
            <div><Label>CPU Limit</Label><Input value={cpuLimit} onChange={(e) => setCpuLimit(e.target.value)} /></div>
          </div>

          <Separator />
          <button onClick={() => setShowAdvanced(!showAdvanced)} className="text-sm font-medium text-primary hover:underline">
            {showAdvanced ? "▾ Hide Advanced" : "▸ Show Advanced"}
          </button>

          {showAdvanced && (
            <div className="space-y-4">
              <div><Label className="mb-2 block">Environment Variables</Label><EnvEditor value={envVars} onChange={setEnvVars} descriptions={envDescriptions} /></div>
              <div>
                <Label className="mb-2 block">Volumes</Label>
                {volumes.map((vol, i) => (
                  <div key={i} className="mb-2 flex gap-2">
                    <Input value={vol.name} onChange={(e) => { const n = [...volumes]; n[i] = { ...vol, name: e.target.value }; setVolumes(n); }} placeholder="Volume name" className="flex-1 font-mono text-xs" />
                    <Input value={vol.mount} onChange={(e) => { const n = [...volumes]; n[i] = { ...vol, mount: e.target.value }; setVolumes(n); }} placeholder="/mount/path" className="flex-1 font-mono text-xs" />
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={gpuEnabled} onCheckedChange={setGpuEnabled} /><Label>GPU Passthrough</Label>
                {gpuEnabled && <Input type="number" value={gpuCount} onChange={(e) => setGpuCount(Number(e.target.value))} className="w-20" min={1} />}
              </div>
              <div><Label>SHM Size</Label><Input value={shmSize} onChange={(e) => setShmSize(e.target.value)} /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Idle Timeout</Label><Input value={idleTimeout} onChange={(e) => setIdleTimeout(e.target.value)} /></div>
                <div><Label>Grace Period</Label><Input value={gracePeriod} onChange={(e) => setGracePeriod(e.target.value)} /></div>
              </div>
            </div>
          )}

          <Separator />
          <div className="flex gap-2">
            <Button onClick={handleSaveAndLaunch} className="flex-1">Save & Launch</Button>
            <Button variant="secondary" onClick={handleSaveTemplate}>Save as Template</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: Wire launch modal into App.tsx**

Replace `frontend/src/App.tsx`:

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import { Header } from "@/components/layout/header";
import { TabNav } from "@/components/layout/tab-nav";
import { InstanceGrid } from "@/components/instances/instance-grid";
import { TemplateGrid } from "@/components/templates/template-grid";
import { RegistryBrowser } from "@/components/templates/registry-browser";
import { LaunchModal } from "@/components/templates/launch-modal";
import { cn } from "@/lib/utils";
import type { Instance, ServiceTemplate, RegistryImage } from "@/lib/types";

export default function App() {
  const [activeTab, setActiveTab] = useState("instances");
  const [templateSubTab, setTemplateSubTab] = useState("registry");
  const [_selectedInstance, setSelectedInstance] = useState<Instance | null>(null);
  const [launchRegistry, setLaunchRegistry] = useState<RegistryImage | null>(null);
  const [launchTemplate, setLaunchTemplate] = useState<ServiceTemplate | null>(null);
  const [launchOpen, setLaunchOpen] = useState(false);

  function handleImportRegistry(image: RegistryImage) {
    setLaunchRegistry(image);
    setLaunchTemplate(null);
    setLaunchOpen(true);
  }

  function handleLaunchTemplate(template: ServiceTemplate) {
    setLaunchTemplate(template);
    setLaunchRegistry(null);
    setLaunchOpen(true);
  }

  function closeLaunchModal() {
    setLaunchOpen(false);
    setLaunchRegistry(null);
    setLaunchTemplate(null);
    setActiveTab("instances");
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 p-6">
        {activeTab === "instances" && (
          <InstanceGrid onSelect={setSelectedInstance} onLaunch={() => setActiveTab("templates")} />
        )}
        {activeTab === "templates" && (
          <div>
            <div className="mb-4 flex gap-1">
              {[
                { id: "registry", label: "LinuxServer Registry" },
                { id: "my-templates", label: "My Templates" },
              ].map((tab) => (
                <button key={tab.id} onClick={() => setTemplateSubTab(tab.id)} className={cn("rounded-lg px-3 py-1.5 text-sm font-medium transition-colors", templateSubTab === tab.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}>
                  {tab.label}
                </button>
              ))}
            </div>
            {templateSubTab === "registry" && <RegistryBrowser onImport={handleImportRegistry} />}
            {templateSubTab === "my-templates" && <TemplateGrid onLaunch={handleLaunchTemplate} />}
          </div>
        )}
      </main>
      <LaunchModal open={launchOpen} onClose={closeLaunchModal} registryImage={launchRegistry} template={launchTemplate} />
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/templates/env-editor.tsx frontend/src/components/templates/launch-modal.tsx frontend/src/App.tsx
git commit -m "feat: launch modal with env editor, advanced config, save/launch"
```

---

## Task 12: Frontend — Instance Detail Modal

**Files:**
- Create: `frontend/src/components/instances/instance-detail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create instance detail modal**

```tsx
// frontend/src/components/instances/instance-detail.tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { StatusBadge } from "./status-badge";
import { api } from "@/api/client";
import { formatDuration } from "@/lib/utils";
import { useStartInstance, useStopInstance, useDeleteInstance } from "@/hooks/use-instances";
import { toast } from "sonner";
import { ExternalLink, Play, Square, Trash2 } from "lucide-react";
import type { Instance } from "@/lib/types";
import { useState } from "react";

interface InstanceDetailProps {
  instance: Instance | null;
  onClose: () => void;
}

export function InstanceDetail({ instance, onClose }: InstanceDetailProps) {
  const start = useStartInstance();
  const stop = useStopInstance();
  const destroy = useDeleteInstance();
  const [imgError, setImgError] = useState(false);

  if (!instance) return null;

  const isRunning = instance.status === "running" || instance.status === "idle";
  const idleSeconds = instance.last_activity ? (Date.now() - new Date(instance.last_activity).getTime()) / 1000 : null;
  const uptimeSeconds = instance.started_at ? (Date.now() - new Date(instance.started_at).getTime()) / 1000 : null;
  const domain = window.location.hostname === "localhost" ? "localhost" : window.location.hostname.split(".").slice(1).join(".");

  function handleDestroy() {
    if (!confirm(`Destroy "${instance.name}"?`)) return;
    destroy.mutate({ id: instance.id, removeVolumes: false }, {
      onSuccess: () => { toast.success("Instance destroyed"); onClose(); },
      onError: (e) => toast.error(`Destroy failed: ${e.message}`),
    });
  }

  return (
    <Dialog open={!!instance} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{instance.name}</DialogTitle></DialogHeader>
        <div className="aspect-video w-full overflow-hidden rounded-lg bg-secondary">
          {isRunning && !imgError ? (
            <img src={`${api.screenshotUrl(instance.id)}?t=${Math.floor(Date.now() / 30000)}`} alt={instance.name} className="h-full w-full object-cover" onError={() => setImgError(true)} />
          ) : (
            <div className="flex h-full items-center justify-center text-5xl text-muted-foreground/30">{instance.status === "stopped" ? "⏸" : "🖥️"}</div>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div><span className="text-muted-foreground">Status</span><div className="mt-1"><StatusBadge status={instance.status} /></div></div>
          <div><span className="text-muted-foreground">Subdomain</span><div className="mt-1 font-mono text-xs">{instance.subdomain}.{domain}</div></div>
          {isRunning && <>
            <div><span className="text-muted-foreground">Uptime</span><div className="mt-1">{formatDuration(uptimeSeconds)}</div></div>
            <div><span className="text-muted-foreground">Idle</span><div className="mt-1">{formatDuration(idleSeconds)}</div></div>
          </>}
        </div>
        {instance.session_config && <>
          <Separator />
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div><span className="text-muted-foreground">Idle Timeout:</span> {instance.session_config.idle_timeout}</div>
            <div><span className="text-muted-foreground">Grace Period:</span> {instance.session_config.grace_period}</div>
            <div><span className="text-muted-foreground">Action:</span> {instance.session_config.timeout_action}</div>
            <div><span className="text-muted-foreground">Never Timeout:</span> {instance.session_config.never_timeout ? "Yes" : "No"}</div>
          </div>
        </>}
        <Separator />
        <div className="flex gap-2">
          {isRunning ? <>
            <Button className="flex-1" onClick={() => window.open(`https://${instance.subdomain}.${domain}`, "_blank")}><ExternalLink className="mr-2 h-3 w-3" /> Connect</Button>
            <Button variant="secondary" onClick={() => stop.mutate(instance.id, { onError: (e) => toast.error(e.message) })}><Square className="mr-2 h-3 w-3" /> Stop</Button>
          </> : (
            <Button className="flex-1" onClick={() => start.mutate(instance.id, { onError: (e) => toast.error(e.message) })}><Play className="mr-2 h-3 w-3" /> Start</Button>
          )}
          <Button variant="destructive" onClick={handleDestroy}><Trash2 className="mr-2 h-3 w-3" /> Destroy</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Wire into App.tsx**

Add import at top:
```tsx
import { InstanceDetail } from "@/components/instances/instance-detail";
```

Change `_selectedInstance` back to `selectedInstance` (remove underscore prefix). Add before closing `</div>` after LaunchModal:
```tsx
<InstanceDetail instance={selectedInstance} onClose={() => setSelectedInstance(null)} />
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/instances/instance-detail.tsx frontend/src/App.tsx
git commit -m "feat: instance detail modal with status, session config, actions"
```

---

## Task 13: Frontend — Docker Integration

**Files:**
- Create: `frontend/nginx.conf`
- Create: `frontend/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create nginx.conf**

```nginx
# frontend/nginx.conf
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
# frontend/Dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
```

- [ ] **Step 3: Add frontend service to docker-compose.yml**

Add to `services:`:

```yaml
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
      - traefik.http.routers.frontend.entrypoints=websecure
      - traefik.http.services.frontend.loadbalancer.server.port=3000
```

Add `screenshots:` to top-level `volumes:`. Add `- screenshots:/app/data/screenshots` to backend service volumes.

- [ ] **Step 4: Commit**

```bash
git add frontend/nginx.conf frontend/Dockerfile docker-compose.yml
git commit -m "feat: frontend Docker integration — Dockerfile, nginx, compose"
```

---

## Task 14: Final Verification and Cleanup

- [ ] **Step 1: Update .gitignore with frontend entries**

Add:
```
node_modules/
dist/
```

- [ ] **Step 2: Run backend tests**

Run: `cd backend && .venv/bin/python -m pytest -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Run frontend TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Update CHANGELOG.md**

Add above existing entry:

```markdown
## [0.2.0] - 2026-05-24

### Added
- React frontend dashboard (Vite + TypeScript + Tailwind + shadcn/ui)
- Instance cards with screenshot thumbnails, status badges, actions
- Template Gallery with LinuxServer.io registry browser
- Launch modal with env editor, volume config, GPU toggle, session settings
- Instance detail modal with status info and inline actions
- Backend: LinuxServer registry proxy with 1hr cache
- Backend: Screenshot capture service for container thumbnails
- Backend: CORS middleware for frontend dev server
- Frontend Docker integration (nginx, Dockerfile, compose service)
```

- [ ] **Step 6: Final commit**

```bash
git add .gitignore CHANGELOG.md
git commit -m "chore: v0.2.0 cleanup — gitignore, changelog"
```
