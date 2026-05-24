# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
