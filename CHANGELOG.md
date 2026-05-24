# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

## [0.1.0] - 2026-05-24

### Added
- FastAPI backend with full container lifecycle management
- SQLModel data layer (ServiceTemplate, Instance, SessionEvent)
- Template CRUD API with JSON seeding from `templates/` directory
- Instance lifecycle endpoints (create, start, stop, destroy, keepalive)
- Docker manager service wrapping docker-py for container/volume operations
- Traefik label generator for automatic reverse proxy routing
- Session monitor with configurable idle detection and auto-stop
- Docker Compose infrastructure (Traefik, Cloudflare Tunnel, Backend)
- Default templates: dev-desktop, workstation, gaming
- 44 passing tests covering all modules
