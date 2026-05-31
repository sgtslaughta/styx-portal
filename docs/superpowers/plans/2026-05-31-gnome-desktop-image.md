# GNOME Desktop Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `selkies-gnome:latest` container image that delivers a stock minimal Ubuntu 26.04 (GNOME 50) desktop over Selkies, alongside the existing XFCE image.

**Architecture:** Clone the proven `images/desktop/` (XFCE) scaffold to `images/gnome-desktop/`. In Pixelflux Wayland mode, Pixelflux is the host Smithay compositor; the session script launches GNOME Shell **nested** (`gnome-shell --wayland --nested`) as a Wayland client of that compositor, so Pixelflux captures it with zero extra plumbing. A new `gnome-desktop` template surfaces it in the Hub.

**Tech Stack:** Docker, `ghcr.io/linuxserver/baseimage-selkies:ubunturesolute`, GNOME 50 / Mutter (nested Wayland), Yaru theme + ubuntu-dock + AppIndicator extensions, Firefox (Mozilla PPA deb), dconf, FastAPI template seeding (JSON).

**Validation note:** This is an image-build artifact. The "test" loop is **build → run container → observe in browser**, not pytest. Tasks are ordered to retire the single real risk (nested Mutter capture) first. No backend code changes are required; template seeding reads the templates dir dynamically and existing tests use isolated payloads, so adding a JSON template breaks nothing.

**Prereq for runtime tasks:** Docker available, ports 3000/3001 free, browser reachable at `http://localhost:3000`. GPU steps require `/dev/dri` and (optionally) `nvidia-smi`.

---

## File Structure

- `images/gnome-desktop/Dockerfile` — FROM ubunturesolute; GNOME package set + Firefox deb; COPY startup + dconf assets.
- `images/gnome-desktop/Makefile` — build/run/stop/clean/logs/shell (IMAGE_NAME=selkies-gnome).
- `images/gnome-desktop/docker-compose.yml` — local dev/test run.
- `images/gnome-desktop/.dockerignore` — trim build context.
- `images/gnome-desktop/root/defaults/startwm_wayland.sh` — session launcher (nested gnome-shell, GPU env, first-run dconf seed).
- `images/gnome-desktop/root/defaults/dconf/00-ubuntu-defaults` — dconf keyfile: Yaru theme, dock, enabled extensions.
- `templates/gnome-desktop.json` — Hub template referencing `selkies-gnome:latest`.

---

## Task 1: Scaffold image + prove nested-Mutter capture (M1, critical risk)

Build the smallest image that can render GNOME Shell through Pixelflux. No fidelity yet — just confirm the architecture holds before investing further.

**Files:**
- Create: `images/gnome-desktop/.dockerignore`
- Create: `images/gnome-desktop/Dockerfile`
- Create: `images/gnome-desktop/root/defaults/startwm_wayland.sh`
- Create: `images/gnome-desktop/Makefile`
- Create: `images/gnome-desktop/docker-compose.yml`

- [ ] **Step 1: Create `.dockerignore`**

```
**/.git
**/*.md
```

- [ ] **Step 2: Create minimal `Dockerfile` (GNOME core only)**

```dockerfile
FROM ghcr.io/linuxserver/baseimage-selkies:ubunturesolute

LABEL maintainer="richardsoto1010@gmail.com"
LABEL description="Minimal GNOME (Ubuntu 26.04) Wayland desktop"

ENV DEBIAN_FRONTEND=noninteractive

# ─── GNOME core (nested Wayland shell) ───────────────────────────────────────
# --no-install-recommends and NO ubuntu-desktop meta → avoids snapd.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnome-shell \
    gnome-session \
    gnome-settings-daemon \
    mutter \
    nautilus \
    gnome-control-center \
    dbus-x11 \
    at-spi2-core \
    dconf-cli \
    && rm -rf /var/lib/apt/lists/*

# ─── Desktop Startup Override ────────────────────────────────────────────────
COPY root/defaults/startwm_wayland.sh /defaults/startwm_wayland.sh
RUN chmod +x /defaults/startwm_wayland.sh

ENV TITLE="GNOME Desktop"
ENV START_DOCKER=false

EXPOSE 3000 3001
VOLUME /config
```

- [ ] **Step 3: Create `root/defaults/startwm_wayland.sh` (bare nested shell)**

```bash
#!/usr/bin/env bash
# GNOME Wayland session — nested gnome-shell inside Pixelflux's Smithay compositor
ulimit -c 0
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_RULES=evdev
export WAYLAND_DISPLAY=wayland-1
export XDG_SESSION_TYPE=wayland

# NVIDIA / GPU acceleration (verbatim from XFCE image)
if command -v nvidia-smi &> /dev/null && [ -e /dev/dri ]; then
    export LIBGL_KOPPER_DRI2=1
    export MESA_LOADER_DRIVER_OVERRIDE=zink
    export GALLIUM_DRIVER=zink
fi

# Launch GNOME Shell nested as a Wayland client of Pixelflux's compositor.
exec dbus-run-session -- gnome-shell --wayland --nested
```

- [ ] **Step 4: Create `Makefile`**

```makefile
.PHONY: build run stop clean logs shell

IMAGE_NAME := selkies-gnome
TAG := latest

build:
	docker build -t $(IMAGE_NAME):$(TAG) .

run: build
	docker compose up -d

stop:
	docker compose down

clean:
	docker compose down -v
	docker rmi $(IMAGE_NAME):$(TAG) 2>/dev/null || true

logs:
	docker compose logs -f

shell:
	docker exec -it selkies-gnome /bin/bash
```

- [ ] **Step 5: Create `docker-compose.yml`**

```yaml
services:
  gnome:
    build: .
    image: selkies-gnome:latest
    container_name: selkies-gnome
    ports:
      - "3000:3000"
      - "3001:3001"
    volumes:
      - gnome-config:/config
    devices:
      - /dev/dri:/dev/dri
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
      - TITLE=GNOME Desktop
      - PIXELFLUX_WAYLAND=true
      - START_DOCKER=false
    restart: unless-stopped

volumes:
  gnome-config:
```

- [ ] **Step 6: Build the image**

Run: `cd images/gnome-desktop && make build`
Expected: build completes, no apt errors, no `snapd` pulled (scan output — `snapd` must NOT appear in installed packages).

- [ ] **Step 7: Run and observe (capture proof — THE gate)**

Run: `cd images/gnome-desktop && make run && make logs`
Then open `http://localhost:3000` in a browser.
Expected: the GNOME Shell desktop (top bar, Activities, default background) renders live in the browser and the mouse/keyboard control it.

If it renders → architecture confirmed, proceed.
If nested Mutter fails to start (check `make logs` for Mutter errors like "Failed to create backend" / no Wayland display), STOP and debug before continuing: try variants `gnome-shell --nested --wayland`, ensure `WAYLAND_DISPLAY` matches Pixelflux's socket (inspect `make shell` → `ls $XDG_RUNTIME_DIR/wayland-*`), confirm `dbus-run-session` present. Do not proceed to fidelity work until capture is proven.

- [ ] **Step 8: Commit**

```bash
git add images/gnome-desktop
git commit -m "feat(image): scaffold minimal nested-GNOME selkies image (M1 capture proof)"
```

---

## Task 2: GPU + stock apps verification (M2)

Confirm default GNOME apps launch and GPU acceleration engages. Mostly runtime verification; the only file change adds the stock 26.04 app set.

**Files:**
- Modify: `images/gnome-desktop/Dockerfile` (add apps layer)

- [ ] **Step 1: Add stock-apps layer to `Dockerfile`**

Insert after the GNOME-core `RUN` block, before the startup COPY:

```dockerfile
# ─── Stock Ubuntu 26.04 GNOME apps ───────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnome-text-editor \
    gnome-system-monitor \
    gnome-calculator \
    loupe \
    papers \
    ptyxis \
    xdg-desktop-portal-gnome \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Rebuild**

Run: `cd images/gnome-desktop && make build`
Expected: build succeeds, no snapd.

- [ ] **Step 3: Run and verify apps**

Run: `make run` then open `http://localhost:3000`.
Open Activities → launch Files (nautilus), Settings (gnome-control-center), Text Editor, and the terminal (ptyxis). 
Expected: each app opens and is interactive. If `ptyxis` fails to launch nested, note it (Task 4 open question) and try `gnome-terminal`/`gnome-console` as fallback.

- [ ] **Step 4: Verify GPU (if hardware present)**

Run: `make shell` then inside the container: `glxinfo -B 2>/dev/null | grep -i "renderer\|vendor"` (install `mesa-utils` ad-hoc if missing) and check `make logs` for zink/GPU init without errors.
Expected: renderer reflects GPU/zink, not pure llvmpipe (when a GPU is passed through). On a GPU-less host, llvmpipe software rendering is acceptable.

- [ ] **Step 5: Commit**

```bash
git add images/gnome-desktop/Dockerfile
git commit -m "feat(image): add stock GNOME apps + portal, verify GPU (M2)"
```

---

## Task 3: Ubuntu fidelity layer — Yaru, dock, AppIndicator, Firefox (M3)

Make it look like stock minimal Ubuntu and persist user settings on the volume.

**Files:**
- Modify: `images/gnome-desktop/Dockerfile` (Yaru/extensions/Firefox + COPY dconf)
- Create: `images/gnome-desktop/root/defaults/dconf/00-ubuntu-defaults`
- Modify: `images/gnome-desktop/root/defaults/startwm_wayland.sh` (theme env + first-run dconf seed)

- [ ] **Step 1: Add Yaru + extensions + Firefox layers to `Dockerfile`**

Insert after the stock-apps layer:

```dockerfile
# ─── Ubuntu look: Yaru theme + dock + appindicator ───────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    yaru-theme-gtk \
    yaru-theme-icon \
    yaru-theme-sound \
    yaru-theme-gnome-shell \
    gnome-shell-extension-ubuntu-dock \
    gnome-shell-extension-appindicator \
    ubuntu-wallpapers \
    fonts-ubuntu \
    && rm -rf /var/lib/apt/lists/*

# ─── Firefox (deb, not snap) — Mozilla PPA, pinned over transition package ────
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:mozillateam/ppa && \
    printf 'Package: *\nPin: release o=LP-PPA-mozillateam\nPin-Priority: 1001\n' > /etc/apt/preferences.d/mozilla-firefox && \
    apt-get update && apt-get install -y --no-install-recommends firefox && \
    rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Create `root/defaults/dconf/00-ubuntu-defaults`**

```ini
[org/gnome/desktop/interface]
gtk-theme='Yaru'
icon-theme='Yaru'
cursor-theme='Yaru'
color-scheme='prefer-dark'
font-name='Ubuntu 11'

[org/gnome/shell]
enabled-extensions=['ubuntu-dock@ubuntu.com', 'ubuntu-appindicators@ubuntu.com']

[org/gnome/desktop/background]
picture-uri='file:///usr/share/backgrounds/warty-final-ubuntu.png'
picture-uri-dark='file:///usr/share/backgrounds/warty-final-ubuntu.png'
```

- [ ] **Step 3: Update `startwm_wayland.sh` with theme env + first-run dconf seed**

Replace the file with:

```bash
#!/usr/bin/env bash
# GNOME Wayland session — nested gnome-shell inside Pixelflux's Smithay compositor
ulimit -c 0
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_RULES=evdev
export WAYLAND_DISPLAY=wayland-1
export XDG_SESSION_TYPE=wayland
export XCURSOR_THEME=Yaru
export XCURSOR_SIZE=24
export GTK_THEME=Yaru

# First-run: seed default dconf into the persisted volume
if [ ! -f /config/.config/.gnome-seeded ]; then
    mkdir -p /config/.config
    dconf load / < /defaults/dconf/00-ubuntu-defaults || true
    touch /config/.config/.gnome-seeded
fi

# NVIDIA / GPU acceleration (verbatim from XFCE image)
if command -v nvidia-smi &> /dev/null && [ -e /dev/dri ]; then
    export LIBGL_KOPPER_DRI2=1
    export MESA_LOADER_DRIVER_OVERRIDE=zink
    export GALLIUM_DRIVER=zink
fi

# Launch GNOME Shell nested as a Wayland client of Pixelflux's compositor.
exec dbus-run-session -- gnome-shell --wayland --nested
```

- [ ] **Step 4: Add the dconf COPY to `Dockerfile`**

Add before the startup-script COPY:

```dockerfile
COPY root/defaults/dconf/ /defaults/dconf/
```

- [ ] **Step 5: Rebuild on a fresh volume**

Run: `cd images/gnome-desktop && make clean && make run && make logs`
(`make clean` drops the old volume so first-run seeding executes.)

- [ ] **Step 6: Verify fidelity**

Open `http://localhost:3000`.
Expected: Yaru dark theme applied, ubuntu-dock visible on the left, AppIndicator area in the top bar, Ubuntu wallpaper. Firefox launches from the dock. Appearance closely matches stock minimal Ubuntu 26.04.

- [ ] **Step 7: Verify persistence**

Change a setting (e.g. wallpaper) in Settings, then `docker compose restart` and reload the browser.
Expected: the change persists (stored under `/config` on the named volume; `.gnome-seeded` prevents re-seeding from clobbering it).

- [ ] **Step 8: Commit**

```bash
git add images/gnome-desktop
git commit -m "feat(image): Yaru + dock + appindicator + Firefox fidelity layer (M3)"
```

---

## Task 4: Hub template + end-to-end integration (M4)

Register the image as a Hub template and verify the full Selkies Hub lifecycle.

**Files:**
- Create: `templates/gnome-desktop.json`

- [ ] **Step 1: Create `templates/gnome-desktop.json`**

Mirror the full `xfce-desktop.json` shape (icon, description, volumes, protocol, session_config) with GNOME identity:

```json
{
  "name": "gnome-desktop",
  "display_name": "GNOME Desktop (Ubuntu 26.04)",
  "image": "selkies-gnome:latest",
  "icon": "🐧",
  "description": "Stock minimal Ubuntu 26.04 GNOME desktop on Wayland with Firefox",
  "env_vars": {
    "PUID": "1000",
    "PGID": "1000",
    "PIXELFLUX_WAYLAND": "true",
    "TITLE": "GNOME Desktop"
  },
  "gpu_enabled": true,
  "gpu_count": 1,
  "memory_limit": "8g",
  "cpu_limit": "4.0",
  "shm_size": "2g",
  "volumes": [
    {"name": "{instance_id}-home", "mount": "/config"}
  ],
  "internal_port": 3000,
  "internal_protocol": "http",
  "category": "desktop",
  "tags": ["desktop", "gnome", "ubuntu", "wayland"],
  "session_config": {
    "idle_timeout": "60m",
    "grace_period": "10m",
    "timeout_action": "stop",
    "never_timeout": false,
    "max_session_duration": null
  }
}
```

- [ ] **Step 2: Verify backend tests still pass (no regression from new template)**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all tests pass (template seeding reads the dir dynamically; tests use isolated payloads, so the new JSON does not change any assertion).

- [ ] **Step 3: Lint**

Run: `cd backend && .venv/bin/python -m ruff check app/ tests/`
Expected: no new findings (no Python changed, but confirm clean per project CI norm).

- [ ] **Step 4: End-to-end via the Hub**

Start the stack (`docker compose up -d` at repo root) so the backend seeds templates. In the Hub UI: confirm "GNOME Desktop (Ubuntu 26.04)" appears, launch an instance, and verify it routes, the live desktop loads, and the instance thumbnail/screenshot captures. Test start/stop/recreate lifecycle as with XFCE.
Expected: GNOME instance behaves identically to an XFCE instance in the Hub.

- [ ] **Step 5: Commit**

```bash
git add templates/gnome-desktop.json
git commit -m "feat(templates): add GNOME Ubuntu 26.04 desktop template"
```

---

## Self-Review

**Spec coverage:**
- New image alongside XFCE → Tasks 1–3 (new `images/gnome-desktop/`), XFCE untouched. ✓
- GNOME Wayland session (nested) → Task 1 Step 3/7. ✓
- Stock minimal Ubuntu look (Yaru/dock/appindicator) → Task 3. ✓
- Firefox deb, no snap → Task 3 Step 1; snapd-absence checks in Task 1 Step 6 / Task 2 Step 2. ✓
- No `ubuntu-desktop` meta → hand-picked packages throughout. ✓
- Reuse XFCE script scaffold → Dockerfile/Makefile/compose/startwm cloned in Task 1. ✓
- Hub template → Task 4. ✓
- Validation milestones M1–M4 → Tasks 1–4 respectively. ✓

**Placeholder scan:** No TBD/TODO; every step has concrete file content or exact command + expected output. Fallbacks (ptyxis→gnome-terminal) are explicit, not vague. ✓

**Type/identity consistency:** `selkies-gnome:latest`, `gnome-desktop`, `IMAGE_NAME=selkies-gnome`, container `selkies-gnome`, volume `gnome-config` (local compose) vs `{instance_id}-home` (Hub template) — local-vs-Hub distinction intentional and matches the XFCE pattern. Extension UUIDs (`ubuntu-dock@ubuntu.com`, `ubuntu-appindicators@ubuntu.com`) consistent between dconf keyfile and intent. ✓

**Open items carried from spec (resolve at runtime, non-blocking):** ubuntu session-mode availability; exact dconf extension UUIDs may need adjustment if package versions differ; ptyxis nested behavior.
</content>
