# Seat Desktop Shell — Design

**Date:** 2026-06-13
**Status:** Approved (brainstorming → spec)
**Scope:** `agent/` only. No backend, no pixelflux/capture changes, no Docker image.

## Problem

The workstation agent's **seat mode** spawns a fresh `labwc` (wlroots) compositor that
pixelflux captures; host apps join it as Wayland clients via `WAYLAND_DISPLAY`. The agent's
`write_seat_config()` (`agent/engine.py`) currently produces a near-empty desktop: a solid-color
`swaybg` background, an unconfigured `waybar` (launched config-less → inert default bar), a
terminal, and a 3-item labwc root menu (Terminal / Reconfigure / Exit).

Consequences (all symptoms of the bare shell):

| Symptom | Cause |
|---|---|
| No click app menu | Only the 3-item labwc right-click root menu; no launcher. |
| Header/panel tools dead | waybar launched with no config → no interactive modules. |
| JetBrains Toolbox & tray apps unusable | No StatusNotifier (SNI) tray host in the seat. |
| No desktop files/folders | wlroots has no desktop-icon manager; background is a flat color. |
| Not dark (host is dark) | Seat is a fresh nested session; nothing pushes theme / `color-scheme` / portal. It never inherits the user's real GNOME config. |

## Constraints (fixed, not in scope to change)

- **pixelflux Wayland capture is wlroots-only** (labwc/sway/wayfire family). A full GNOME-Shell /
  KWin session cannot be the seat compositor.
- **Mirror mode (capturing the user's real desktop) is X11-only** today (`XShm` capture,
  `engine.py`). It cannot grab a Wayland host, which is why the user is on seat mode.
- Therefore: improve the **labwc seat shell** in place. True icons-on-the-background remain
  impossible on wlroots and are **out of scope** (answered via dock + file manager instead).

## Goal

Transform the seat into a GNOME-like desktop: top panel, full-screen app grid, bottom dock,
working system tray (Toolbox docks), and dark mode — with graceful degradation when optional
binaries are absent.

Chosen layout (approved):
- **Top bar + dock** — waybar across the top, `nwg-dock` auto-hide dock at the bottom.
- **Full-screen app grid** — `nwg-drawer` (GNOME-Activities-like), triggered by the panel menu
  button and the **Super** key.
- **Dark theme** — Adwaita-dark (zero-dep, ships with GTK) + `prefer-dark` so any host-installed
  theme can win.
- **File manager** — reuse the host's if present, else install Thunar.

## Architecture

### Config isolation

The seat runs as the **user's own host account**, so it must not clobber the user's real
`~/.config`. styx_agent launches `labwc -C $INSTALL_DIR/labwc` (`styx_agent.py:166`). labwc reads
its own config from that `-C` path; waybar is launched from autostart with **explicit
`-c $INSTALL_DIR/waybar/config -s $INSTALL_DIR/waybar/style.css`** paths, and nwg-drawer/nwg-dock
take CLI flags (no config files). We deliberately do **not** set `XDG_CONFIG_HOME` — doing so would
redirect the user's own host apps (browser profiles, etc.) away from `~/.config` and break them.
The user's real `~/.config` is never read or written; `styx_agent.py` is unchanged.

### Component map

```
$INSTALL_DIR/                       (explicit config root — no XDG_CONFIG_HOME export)
  labwc/
    rc.xml          dark border theme; Super → nwg-drawer keybind
    environment     GTK_THEME=Adwaita-dark, XCURSOR_THEME, QT_QPA_PLATFORM=wayland, …
    menu.xml        root menu auto-built from installed .desktop apps + Files/Terminal/Exit
    autostart       see below
  waybar/
    config          top bar modules
    style.css       dark styling
  nwg-dock/         dock style/pins (if used)
```

**labwc `autostart`** (regenerated each shell start, as today, so newly installed tools are
picked up on restart) runs, each guarded by `shutil.which`:
1. `swaybg` — wallpaper.
2. dark-mode push — `gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'` plus
   `gtk-theme`/`icon-theme`/`cursor-theme`; ensure `xdg-desktop-portal` + `xdg-desktop-portal-gtk`
   are running so `org.freedesktop.appearance` reports dark (Firefox/Chrome/GTK4/Electron honor it).
3. `waybar` — top panel (`-c $INSTALL_DIR/waybar/config -s …/style.css` or via XDG).
4. `nwg-dock` — bottom auto-hide dock; pins: launcher, terminal, file manager, browser.

**waybar `config`** modules:
- Left: `custom/menu` button → `exec nwg-drawer`.
- Center: `clock`.
- Right: `wlr/taskbar`, `tray` (SNI host — Toolbox/Chrome/etc. dock here), `pulseaudio`,
  `network`, `custom/power`.

All waybar modules are native; **no extra packages** beyond waybar itself.

### Dependencies (added to `SEAT_PKG` in `enroll.sh`, per-distro mapped)

| Package | Purpose | Notes |
|---|---|---|
| `nwg-drawer` | full-screen app grid | fallback to `fuzzel` if absent |
| `nwg-dock` | bottom dock | skipped if absent |
| `fuzzel` | fallback launcher | widely packaged; guarantees a working launcher |
| `thunar` | file manager | only meaningful if host lacks one (runtime detection) |
| `xdg-desktop-portal-gtk` | portal color-scheme → dark in GTK4/sandboxed/browser apps | |
| `gnome-themes-extra` | Adwaita-dark for GTK2/3 | |
| `adwaita-icon-theme` | icon theme | usually present |

Existing seat deps stay: `labwc xwayland waybar swaybg foot wl-clipboard`.

Package-name mapping required for `apt`, `dnf`, `pacman`, `zypper` (some names differ; where a
package is unavailable on a manager, omit it — degradation covers it).

### Graceful degradation

Every component is `shutil.which`-guarded (existing pattern in `write_seat_config`). Behavior when
binaries are missing:
- **Launcher chain:** `nwg-drawer` → `fuzzel` → labwc root menu (`menu.xml`). The Super keybind and
  waybar menu button target whichever is present.
- **Dock:** `nwg-dock` absent → no dock; pinned apps still reachable via the launcher/menu.
- **enroll:** missing packages produce a `WARNING (E03)` and never fail enrollment.

### Files / folders need (no desktop-background icons)

Satisfied without wlroots desktop icons:
- File manager pinned in the dock and present in the app grid.
- labwc root `menu.xml` gains a **Files** entry → opens `$HOME` in the detected file manager.
- File-manager detection order: host `nautilus`/`nemo`/`thunar`/`pcmanfm-qt` → else installed Thunar.

## Testing

`agent/tests/test_engine.py`, mocking `shutil.which` + filesystem:
- autostart emits waybar + nwg-dock + nwg-drawer launches when those binaries are present.
- autostart emits dark-mode `gsettings` lines + portal start.
- configs written under the isolated `$INSTALL_DIR` (XDG) path, not `~/.config`.
- `menu.xml` generated from discovered `.desktop` files; includes Files/Terminal/Exit.
- launcher fallback chain: drawer absent → fuzzel; both absent → root menu only.
- waybar `config` contains the `tray` module (Toolbox docking).

## Out of scope

- Desktop-background icons (wlroots limitation).
- Mirror mode / Wayland-real-desktop capture.
- pixelflux capture, backend, Docker desktop image.

## Touch list

- `agent/enroll.sh` — extend `SEAT_PKG` (+ per-distro maps) with the new deps.
- `agent/engine.py` — rewrite `write_seat_config()`; add `.desktop`-scan menu builder, waybar/dock
  config generators, dark-mode autostart lines, file-manager detection.
- `agent/tests/test_engine.py` — coverage above.

(`agent/styx_agent.py` is unchanged — see Config isolation.)
