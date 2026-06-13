# Agent & Workstation Desktop Build

How the Styx workstation agent is built, packaged, and how the **seat-mode
desktop** is assembled — plus the reasoning behind each decision. For operator
tasks (enroll, connect, troubleshoot) see [WORKSTATIONS.md](WORKSTATIONS.md).

## 1. The two capture modes

The agent (`agent/styx_agent.py` + `agent/engine.py`) streams a workstation in
one of two modes, auto-detected at enrollment:

| Mode | What is captured | When used |
|------|------------------|-----------|
| **mirror** | A live **X11** display via XShm capture. Resolution locked to the physical screen (never xrandr-resizes the user's monitor). | Host has a running X11 session and mirror isn't disabled. |
| **seat** | A **private Wayland desktop** that runs alongside the login session; the physical screen is untouched. | Host is Wayland, headless, or mirror is disabled. |

> **Why mirror is X11-only:** mirror attaches to an existing X server with XShm.
> There is no equivalent live-attach for an arbitrary Wayland compositor (no
> standard "capture someone else's session" path), so a Wayland host always uses
> **seat** mode. This is why most modern desktops land on seat mode.

## 2. Seat desktop architecture

Seat mode builds a desktop from scratch each time the streaming shell starts:

```
pixelflux  (outer compositor, Smithay) ── captures + encodes ──> browser
   └── seat Wayland socket (wayland-N)
         └── labwc  (nested WM, reads our generated config in $INSTALL_DIR/labwc)
               ├── swaybg            wallpaper (bginfo PNG)
               ├── waybar (top)      Apps button · clock · tray (SNI) · audio · network
               ├── waybar (bottom)   dock: pinned Apps/Files/Web/Term + open-window taskbar
               ├── nwg-drawer        full-screen app grid (Super / Super+D / Apps)
               ├── xdg-desktop-portal(+gtk)  Settings → color-scheme=prefer-dark
               └── host apps         join the seat socket as Wayland clients
```

- **pixelflux** is the outer compositor that is actually captured and streamed.
- **labwc** runs *nested* on the seat socket as the window manager the user sees.
  We generate its entire config on every shell start (`engine.write_seat_config`)
  so newly installed tools are picked up on restart.
- Config generators are **pure functions** in `engine.py` (`build_waybar_config`,
  `build_waybar_dock`, `build_root_menu`, `build_labwc_rc`,
  `build_labwc_environment`, `build_autostart`, `wallpaper_convert_cmd`) — each
  unit-tested in `agent/tests/test_engine.py`.

### Config isolation

The seat runs as the **user's own account**, so it must not clobber the user's
real `~/.config`. We do **not** set `XDG_CONFIG_HOME`. Instead labwc is launched
with `-C $INSTALL_DIR/labwc`, and each waybar is launched with explicit
`-c/-s` paths under `$INSTALL_DIR/waybar`. Setting `XDG_CONFIG_HOME` would
redirect the user's *own* apps (browser profiles, etc.) away from `~/.config`.

## 3. Server-built artifacts

Workstations never compile anything or add third-party apt sources. Everything
that isn't in the distro's official repos is **built once on the server** and
pulled at enroll. Built by `scripts/build_agent_artifacts.sh` (run on the portal
host; needs only Docker), registered in
`backend/app/services/artifacts.py::ARTIFACTS`, served at
`/api/enroll/artifacts/{name}`, and pulled+extracted by `enroll.sh`.

| Artifact | Contents | Build method |
|----------|----------|--------------|
| `wheelhouse-x86_64.tar.gz` | Python wheels (selkies, pixelflux, pcmflux, …) for cp310–cp313 | manylinux container |
| `selkies-web.tar.gz` | Dashboard web dist | extracted from linuxserver image |
| `libshim-x86_64.tar.gz` | libva 2.22 + libwayland-server 1.23 | pinned Ubuntu debs |
| `nwg-shell-x86_64.tar.gz` | `nwg-drawer` binary | `golang:1.25` + GTK3 dev container |

> **Why server-built, not PPA or on-host toolchain:** enrolled machines stay
> clean and trusted — no extra apt sources, no compilers (Go, etc.) installed on
> user boxes. The build host carries the toolchain inside a throwaway Docker
> stage; the workstation only ever downloads a finished binary.

The `nwg-shell` artifact extracts to `$INSTALL_DIR/bin`, which `styx_agent.py`
prepends to `PATH` at startup so `pick_launcher` (and the seat shell) find it.

### Refreshing artifacts

```bash
# On the portal host:
scripts/build_agent_artifacts.sh            # rebuilds all four into ./data/artifacts
# then place them where the backend serves them (ARTIFACT_CACHE_DIR=/app/data/artifacts):
docker cp data/artifacts/nwg-shell-x86_64.tar.gz remote-access-backend-1:/app/data/artifacts/
```

## 4. Decision log (the "why")

**labwc as the seat WM.** Lightweight, openbox-style, runs cleanly *nested* on
pixelflux's socket. Full desktop shells (GNOME Shell, KWin) expect to *be* the
compositor and are heavy; they aren't a good fit as a nested, captured session.

**nwg-drawer for the app grid, built on the server.** It gives the GNOME-style
full-screen app grid, but it isn't packaged on every distro (e.g. **absent from
Ubuntu 24.04**). Rather than a PPA or installing Go on the workstation, we build
it server-side and ship the binary.

**nwg-drawer pinned to v0.5.2.** v0.6+ switched from GTK3 (`gotk3` +
`gtk-layer-shell`) to **GTK4** (`gotk4` + `gtk4-layer-shell`). The GTK4
layer-shell runtime libs are **not available on Ubuntu 24.04**, so a v0.6+ binary
would fail to load there. v0.5.2 is the last GTK3 release; its runtime
(`libgtk-3-0` + `libgtk-layer-shell0`) is present everywhere. `fuzzel` is the
fallback launcher if the binary is missing; the labwc root menu is the final
fallback.

**Bottom waybar dock instead of nwg-dock.** `nwg-dock` is **sway-only** — it
talks the sway IPC (`$SWAYSOCK`) to list tasks and **fatals under labwc**
(`Couldn't list tasks: $SWAYSOCK is empty`). The dock is therefore a *second
waybar* at the bottom: pinned Apps/Files/Web/Term launch buttons plus
`wlr/taskbar` icons of open windows — pure wlroots, no sway dependency. The top
bar drops its taskbar so windows live only on the dock.

**Per-package dependency install.** `enroll.sh`'s `install_pkgs` installs one
package at a time. A single name a distro lacks would otherwise abort the whole
`apt-get install`, silently leaving even the available packages uninstalled.

**Dark mode three ways.** (1) `GTK_THEME=Adwaita-dark` in the labwc
`environment` forces GTK3 apps dark; (2) `gsettings color-scheme prefer-dark` is
pushed at autostart; (3) `xdg-desktop-portal` + `xdg-desktop-portal-gtk` are
launched **from `/usr/libexec`** (they aren't on `PATH`) so the
`org.freedesktop.portal.Settings` interface serves `color-scheme=1` — that is
what GTK4/Electron/**browsers** read. Missing the portal was why browsers stayed
light.

**No Exit button on the top bar.** A `labwc --exit` button tore down the seat UI
while the agent kept supervising — leaving no way back without restarting the
agent. Removed.

**No desktop-background icons.** wlroots/labwc has no desktop-icon manager
(`xfdesktop`/Nautilus-desktop are X11-only). Files/folders are reached via the
dock's Files button, the app grid, and the labwc root menu instead.

**bginfo wallpaper + wave field.** `swaybg` shows a PNG rendered by ImageMagick
at shell start: the **hostname** (large) + **IP** + **OS** bottom-right (Windows
bginfo style), over a full-canvas **subtle dark-grey sine-wave field** echoing
the login RippleCanvas brand. There is no static logo SVG in the codebase, so
the wave is drawn from computed sine polylines (`wave_polylines`). If ImageMagick
is absent, it falls back to a flat colour.

## 5. Seat dependencies

Installed by `enroll.sh` (`SEAT_PKG`, per package manager), all from official
repos:

`labwc xwayland waybar swaybg foot wl-clipboard fuzzel thunar
xdg-desktop-portal-gtk gnome-themes-extra adwaita-icon-theme libgtk-layer-shell0
imagemagick` (+ VAAPI driver). `nwg-drawer` arrives as the server artifact, not
apt. Every launch line in the generated autostart is `command -v`-guarded, so a
host missing any optional tool still gets a working (barer) session.

## 6. References

- Specs/plans: `docs/superpowers/specs/2026-06-13-seat-desktop-shell-design.md`,
  `docs/superpowers/plans/2026-06-13-seat-desktop-shell.md`
- Code: `agent/engine.py`, `agent/styx_agent.py`, `agent/enroll.sh`,
  `scripts/build_agent_artifacts.sh`, `backend/app/services/artifacts.py`
- Tests: `agent/tests/test_engine.py`, `backend/tests/test_artifacts.py`
