# Selkies Hub — Frontend Dashboard Design Spec

**Date:** 2026-05-24
**Scope:** React frontend hub (Sub-project 2 of 4)
**Status:** Draft

## Overview

Single-page React dashboard for managing Selkies remote desktop containers. Provides instance management with live screenshot thumbnails, a LinuxServer.io registry browser for importing templates, and a custom template editor.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Vite + React 18 + TypeScript |
| Styling | Tailwind CSS 4 |
| Components | shadcn/ui |
| Data Fetching | TanStack Query (5s polling) |
| Routing | React Router v7 (tab-based, minimal) |
| Theme | System-adaptive, dark default |
| Icons | Lucide React |

## Layout

Minimal tabs + card grid (Layout C):

```
┌─────────────────────────────────────────────��───┐
│ ⚡ Selkies Hub          3 running · 2 stopped  ⚙️│
├─────────────────────────────────────────────────┤
│ [My Instances] [Template Gallery]               │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ screenshot│  │ screenshot│  │ screenshot│     │
│  │ thumbnail │  │ thumbnail │  │ thumbnail │     │
│  │           │  │           │  │           │     │
│  │ 🖥️ Dev    │  │ 🏗️ Work   │  │ 🎮 Gaming │     │
│  │ ● Running │  │ ● Running │  │ ● Stopped │     │
│  │ 5m idle   │  │ 12m idle  │  │           │     │
│  │[Connect][⋯]│  │[Connect][⋯]│  │[Start] [⋯]│     │
│  └──────────┘  └──────────┘  └──────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Pages / Views

### 1. My Instances (default tab)

Card grid showing all instances. Each card:
- **Screenshot thumbnail** (from `GET /api/instances/{id}/screenshot`, placeholder when stopped)
- Instance name + icon
- Status badge: running (green), idle (amber), stopped (gray), error (red)
- Idle time (when running)
- Primary action: **Connect** (running → opens subdomain in new tab) or **Start** (stopped)
- Overflow menu: Stop, Destroy (with confirmation), Session settings

**Empty state:** "No instances yet. Browse the Template Gallery to launch one."

Auto-refreshes every 5s via TanStack Query.

### 2. Template Gallery (tab)

Two sub-sections via secondary tabs:

#### LinuxServer Registry

- Fetches from `GET /api/registry/images` (backend proxy of LinuxServer API)
- Filterable by category (Network, Media, DNS, Tools, etc.)
- Searchable by name/description
- Card per image showing: project_logo, name, description, category badges, stars, monthly_pulls
- Click → opens **Launch/Import modal**

#### My Templates

- Saved templates from backend `GET /api/templates`
- Same card layout with edit/delete actions
- "Create Custom Template" button → blank template editor

### 3. Launch/Import Modal

Two-step flow:

**Step 1 — Basic Config:**
- Name (pre-filled from registry or blank)
- Subdomain (auto-generated from name, editable)
- Memory limit, CPU limit (sensible defaults)

**Step 2 — Advanced (toggle):**
- Environment variables (key/value editor, pre-filled from registry config)
- Volume mounts (path editor, pre-filled)
- Port mappings
- GPU: enable toggle, count selector
- SHM size
- Privileged mode toggle
- Session config: idle timeout, grace period, timeout action, never_timeout, max duration
- Devices (from registry config)

**Actions:**
- "Save as Template" — saves to My Templates for reuse
- "Launch Instance" — saves template + immediately creates and starts instance
- "Save & Launch" — both

### 4. Instance Detail (modal or slide-over)

Accessed via clicking instance card (not the Connect button):
- Full screenshot (larger)
- Status, uptime, idle time
- Session config (editable inline)
- Resource info (memory limit, CPU, GPU)
- Template it was created from
- Actions: Start/Stop/Destroy, Keepalive, Connect

## Backend Additions Required

### Screenshot System

New endpoint + background task:

```
GET /api/instances/{id}/screenshot
Response: image/png (cached screenshot) or 404 if unavailable
```

Implementation:
- Background task captures screenshots every 30s for running instances
- Selkies containers expose HTTP endpoint for screenshots (typically at container_ip:3001/screenshot or similar internal path)
- Backend fetches via Docker network, caches as PNG on disk
- Serves cached image; returns placeholder/404 when stopped

### LinuxServer Registry Proxy

```
GET /api/registry/images
  Query params: ?category=Network&search=vpn
  Response: cached JSON from LinuxServer API (TTL: 1 hour)

GET /api/registry/images/{name}
  Response: single image details with full config
```

Why proxy:
- Avoids CORS issues from frontend direct fetch
- Adds caching (1hr TTL) to reduce external API calls
- Can transform/normalize response for frontend consumption

## Component Architecture

```
src/
├── main.tsx                    # App entry, providers
├── App.tsx                     # Layout shell, tab routing
├── api/
│   └── client.ts              # Fetch wrapper, base URL config
├── hooks/
│   ├── use-instances.ts       # TanStack Query: list, mutations
│   ├── use-templates.ts       # TanStack Query: list, CRUD
│   ├── use-registry.ts        # TanStack Query: LinuxServer API
│   └── use-screenshot.ts      # Image URL with refresh
├── components/
│   ├── ui/                    # shadcn components (Button, Card, Dialog, etc.)
│   ├── layout/
│   │   ├── header.tsx         # Logo, status summary, settings
│   │   └── tab-nav.tsx        # My Instances | Template Gallery
│   ├── instances/
│   │   ├── instance-grid.tsx  # Responsive card grid
│   │   ├── instance-card.tsx  # Single instance card with screenshot
│   │   ├── instance-detail.tsx # Detail modal/slide-over
│   │   └── status-badge.tsx   # Colored status indicator
│   └── templates/
│       ├── template-grid.tsx  # Template cards
│       ├── registry-browser.tsx # LinuxServer browser with search/filter
│       ├── launch-modal.tsx   # Create/launch form (basic + advanced)
│       └── env-editor.tsx     # Key/value env var editor
├── lib/
│   ├── types.ts               # TypeScript interfaces matching API
│   └── utils.ts               # cn(), formatDuration(), etc.
└── styles/
    └── globals.css            # Tailwind directives, theme vars
```

## Data Flow

```
LinuxServer API (external)
       ↓ (cached proxy)
Backend /api/registry/images
       ↓
Frontend TanStack Query ←→ Backend /api/templates
                        ←→ Backend /api/instances
                        ←→ Backend /api/instances/{id}/screenshot
       ↓
React Components (re-render on cache invalidation)
```

Polling: TanStack Query `refetchInterval: 5000` on instance list.
Screenshots: `<img>` tag with cache-busting query param on 30s interval.

## Theme System

- CSS variables for colors, set via class on `<html>`
- `dark` class by default, respects `prefers-color-scheme`
- Toggle in settings (persisted to localStorage)
- Tailwind `darkMode: 'class'`

## Responsive Behavior

- **Desktop (≥1024px):** 3-column card grid
- **Tablet (768-1023px):** 2-column grid
- **Mobile (<768px):** 1-column stack, smaller cards

## Error States

- API unreachable: banner at top "Backend unavailable — retrying..."
- Instance action fails: toast notification with error message
- Screenshot unavailable: gradient placeholder with instance icon
- Registry unavailable: "Could not load LinuxServer registry" with retry button

## Docker Integration

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

Nginx proxies `/api/*` to backend service, serves SPA for all other routes.

Docker Compose addition:
```yaml
frontend:
  build: ./frontend
  networks:
    - selkies-hub
  labels:
    - traefik.enable=true
    - traefik.http.routers.frontend.rule=Host(`${DOMAIN}`)
    - traefik.http.routers.frontend.entrypoints=websecure
    - traefik.http.services.frontend.loadbalancer.server.port=3000
```

## Design Decisions

1. **TanStack Query over manual fetch** — automatic caching, polling, cache invalidation, optimistic updates
2. **Backend proxy for LinuxServer API** — avoids CORS, adds caching, normalizes data
3. **Screenshots via backend** — containers only accessible on Docker network, not directly from browser
4. **Tabs over router pages** — single-page feel, no full page transitions for a dashboard
5. **shadcn/ui over full component library** — copy-paste ownership, no version lock-in, fully customizable
6. **Modal for launch flow** — keeps context (you can see your instances behind it), avoids navigation
7. **5s polling over WebSocket** — simpler implementation, sufficient for single-user system, easy to change later
