# GNOME Desktop Image — Design

**Date:** 2026-05-31
**Status:** Approved (design)
**Goal:** Add a GNOME-based Selkies desktop image that gets as close as possible to the standard **minimal Ubuntu 26.04 (Resolute Raccoon)** desktop experience, alongside the existing XFCE image.

## Summary

Create a new container image `selkies-gnome:latest` under `images/gnome-desktop/`, built by cloning the proven `images/desktop/` (XFCE) scaffold and swapping the desktop environment. A new `gnome-desktop` template exposes it in the Hub. The existing XFCE image is left untouched.

## Requirements

1. **New image alongside XFCE** — do not replace the working XFCE image.
2. **GNOME Wayland session** — the base (`ubunturesolute`) is Pixelflux-Wayland only; no X11.
3. **Stock minimal Ubuntu look** — Yaru theme, ubuntu-dock, AppIndicator, default GNOME apps. Close to `ubuntu-desktop-minimal` *appearance* without the snap baggage.
4. **Firefox included** — installed from Mozilla's PPA `.deb` (not snap).
5. **No snaps** — snapd is broken in this container (no systemd). Hand-pick GNOME packages instead of the `ubuntu-desktop-minimal` meta.
6. **Reuse the XFCE startup-script scaffold** — same `/defaults/startwm_wayland.sh` override pattern, first-run config copy into `/config`, GPU/zink env block.

## Key Architecture Finding

In Pixelflux Wayland mode, **Pixelflux itself is the host Wayland compositor** (Smithay-based), exposing a Wayland socket at `WAYLAND_DISPLAY=wayland-1`. The XFCE image runs `startxfce4 --wayland` → labwc **nested** as a Wayland client inside that socket. Pixelflux captures its **own** framebuffer (zero-copy GBM → dmabuf → NVENC/VA-API).

Consequence: GNOME does **not** need to expose a screen-capture protocol (wlr-screencopy) or a screencast portal — the capability Mutter notoriously lacks. It only needs to run **Mutter nested as a Wayland client** of Pixelflux's compositor, via `gnome-shell --wayland --nested`. Capture remains entirely Pixelflux's responsibility. This is the standard GNOME-Shell development nesting mode, so feasibility is high.

**Primary risk** (front-loaded in the plan): confirming that nested Mutter launches and renders correctly into Pixelflux's Smithay socket, and that dynamic resolution / GPU passthrough behave. Everything else (fidelity, apps) is low-risk apt + dconf work.

## Components

```
images/gnome-desktop/
├── Dockerfile                       # FROM ubunturesolute; GNOME packages + Firefox deb
├── Makefile                         # build/run/stop/clean (IMAGE_NAME=selkies-gnome)
├── docker-compose.yml               # local dev/test
├── .dockerignore
└── root/defaults/
    ├── startwm_wayland.sh           # session launcher (nested gnome-shell/session)
    ├── dconf/                       # default dconf settings (theme, dock, extensions)
    │   └── 00-ubuntu-defaults       # dconf keyfile applied on first run
    └── (wallpaper asset if needed)

templates/gnome-desktop.json         # Hub template referencing selkies-gnome:latest
```

### Dockerfile (swaps from XFCE)

**Reused verbatim:** base image, `DEBIAN_FRONTEND=noninteractive`, Firefox Mozilla-PPA block (lines 28–34 of XFCE Dockerfile), startup-script COPY+chmod pattern, `EXPOSE 3000 3001`, `VOLUME /config`, env scaffold.

**Replaced:** the XFCE/dev-stack apt layers with a GNOME package set:

- Core: `gnome-shell gnome-session gnome-settings-daemon mutter`
- Apps (stock 26.04): `nautilus gnome-control-center gnome-text-editor ptyxis loupe papers gnome-system-monitor` (`gnome-calculator` optional)
- Ubuntu look: `yaru-theme-gtk yaru-theme-icon yaru-theme-sound yaru-theme-gnome-shell gnome-shell-extension-ubuntu-dock gnome-shell-extension-appindicator ubuntu-wallpapers`
- Plumbing: `xdg-desktop-portal-gnome dbus-x11 at-spi2-core dconf-cli fonts-ubuntu`
- `--no-install-recommends` throughout; **never** install `snapd`, `gnome-software`, or the `ubuntu-desktop*` meta.

**Dropped:** zsh/oh-my-zsh, Chrome, terminator, build-essential/cmake/uv and other XFCE dev tooling (out of scope: stock minimal).

### Startup script (`startwm_wayland.sh`)

Keep the XFCE skeleton; change first-run copy + final exec.

```bash
#!/usr/bin/env bash
ulimit -c 0
export XCURSOR_THEME=Yaru
export XCURSOR_SIZE=24
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_RULES=evdev
export WAYLAND_DISPLAY=wayland-1
export XDG_SESSION_TYPE=wayland
export GNOME_SHELL_SESSION_MODE=ubuntu   # if ubuntu session mode present
export GTK_THEME=Yaru

# First-run: seed default dconf / config into the persisted volume
if [ ! -f /config/.config/.gnome-seeded ]; then
    mkdir -p /config/.config
    # apply packaged dconf defaults (theme, dock, enabled extensions)
    dconf load / < /defaults/dconf/00-ubuntu-defaults || true
    touch /config/.config/.gnome-seeded
fi

# NVIDIA GPU acceleration (verbatim from XFCE image)
if command -v nvidia-smi &> /dev/null && [ -e /dev/dri ]; then
    export LIBGL_KOPPER_DRI2=1
    export MESA_LOADER_DRIVER_OVERRIDE=zink
    export GALLIUM_DRIVER=zink
fi

# Launch GNOME Shell nested as a Wayland client of Pixelflux's compositor.
# Milestone 1 (prove capture): bare nested shell.
exec dbus-run-session -- gnome-shell --wayland --nested
# Milestone 2 (fidelity): graduate to full session, e.g.
#   exec dbus-run-session -- gnome-session --session=ubuntu
```

The dynamic-resolution concern (XFCE deletes `displays.xml`) maps to: do not pin a Mutter monitor config; nested Mutter follows the parent surface size Pixelflux provides.

### Template (`templates/gnome-desktop.json`)

Mirror `xfce-desktop.json`, changing identity + image:

```json
{
  "name": "gnome-desktop",
  "display_name": "GNOME Desktop (Ubuntu 26.04)",
  "image": "selkies-gnome:latest",
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
  "internal_port": 3000,
  "category": "desktop",
  "tags": ["desktop", "gnome", "ubuntu", "wayland"]
}
```

## Data Flow

Browser ⇄ Selkies WebRTC (`:3000`) ⇄ Pixelflux (Smithay compositor + encoder) ⇄ nested Mutter/GNOME Shell ⇄ GNOME apps. Identical to the XFCE path except the nested compositor is Mutter instead of labwc.

## Testing / Validation

This is an image-build artifact, not application code — validation is empirical, staged to retire risk early:

1. **M1 — Capture proof (critical):** Build a stripped image (GNOME core only, no fidelity layer). Launch container with `PIXELFLUX_WAYLAND=true`. Confirm the browser shows the live GNOME Shell desktop and input works. *Gate: if nested Mutter cannot render into Pixelflux, revisit before any further work.*
2. **M2 — App + GPU check:** Launch Files, Settings, Ptyxis, Firefox. With a GPU present, confirm zink acceleration and no crashes.
3. **M3 — Fidelity:** Apply Yaru theme, ubuntu-dock, AppIndicator via dconf; confirm appearance matches stock Ubuntu 26.04 minimal. Confirm settings persist across container restart (volume seeding works).
4. **M4 — Hub integration:** Seed `gnome-desktop` template; launch an instance through the Hub UI; confirm routing, screenshot/thumbnail capture, and lifecycle (start/stop/recreate) work as with XFCE.

No backend/pytest changes expected; the new template JSON is picked up by existing seeding logic. If template seeding has a test asserting a fixed template count, update it.

## Out of Scope

- Replacing or modifying the XFCE image.
- Dev tooling (shells, build tools, extra browsers).
- GNOME Wayland-native (non-nested) capture or screencast-portal paths.
- GDM / login screen (session launched directly, no display manager).
- Snap support.

## Open Questions (resolve during implementation)

- Whether the `ubuntu` gnome-session mode is available as a package in the base and worth using vs. plain `gnome-shell --nested` for M1.
- Exact dconf keys for enabling ubuntu-dock + AppIndicator extensions headlessly (no user toggling).
- Whether `ptyxis` (26.04 default terminal) works nested, or fall back to `gnome-terminal`/`gnome-console`.
</content>
</invoke>
