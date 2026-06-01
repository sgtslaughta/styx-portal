# Dev Workstation Image — Design

**Date:** 2026-05-31
**Status:** Approved (design)
**Goal:** Turn the existing XFCE Selkies image (`images/desktop/`) into a lean **developer workstation** — common dev tools prefilled, no office/email/media fluff, dark theme.

## Context / Why XFCE

A GNOME-Shell variant was attempted and abandoned: GNOME Shell 50.1 hard-requires a session registered via `org.gnome.SessionManager`, and GNOME 50's `gnome-session` registers **only through systemd user units**. The Selkies base (`ghcr.io/linuxserver/baseimage-selkies:ubunturesolute`) is **s6-based, no systemd, Wayland-only** — a hard wall for GNOME Shell. (Mutter itself nests in Pixelflux fine; the blocker is session management.) Full root-cause chain in `2026-05-31-gnome-desktop-image-design.md`. XFCE works today on this base, so we build the workstation on it.

## Requirements

1. Extend the **existing** `images/desktop/` image (decision: one image, not a new sibling). Identity shifts from generic desktop → dev workstation.
2. Prefilled dev tools, no fluff: **no office software, email, media players**.
3. Must include: Firefox, Chrome, npm (Node), Python, git, curl, dark theme, VSCode, PyCharm (Community), nano, btop, htop.
4. No snaps (base has no systemd; matches existing deb-only approach).

## Current State (already in `images/desktop/`)

Present and reused as-is: XFCE Wayland + Selkies, Firefox (Mozilla PPA deb), Google Chrome (deb), `python3/pip/venv/dev`, `git/git-lfs`, `curl/wget`, `build-essential/cmake/ninja/pkg-config`, `zsh + oh-my-zsh`, `fzf/ripgrep/bat/eza/htop/ncdu/tmux`, `uv`, `jq`. No office/email/media packages exist today — nothing to strip.

## Gap → Additions

| Tool | Status | Install method (deb / tarball, no snap) |
|---|---|---|
| Node + npm | missing | NodeSource `setup_22.x` apt repo → `nodejs` |
| VSCode | missing | Microsoft apt repo → `code` (provides `.desktop`) |
| PyCharm Community | missing | JetBrains tarball → `/opt/pycharm` + symlink + `.desktop` |
| nano | missing | apt |
| btop | missing | apt |
| Yaru dark theme | missing | apt `yaru-theme-gtk yaru-theme-icon`; set in xsettings |
| htop | present | — |

## Components / Changes

```
images/desktop/Dockerfile                     # add: node, vscode, pycharm, nano, btop, yaru theme
images/desktop/root/defaults/xfce4/xfconf/
    xfce-perchannel-xml/xsettings.xml         # Adwaita-dark → Yaru-dark
templates/dev-desktop.json                    # refresh description/tags (image ref unchanged)
```

### Dockerfile additions (appended as new layers; existing layers untouched)

**Node 22 (NodeSource):**
```dockerfile
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*
```

**VSCode (Microsoft repo):**
```dockerfile
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list && \
    apt-get update && apt-get install -y --no-install-recommends code && \
    rm -rf /var/lib/apt/lists/*
```

**nano + btop + Yaru theme:**
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano btop yaru-theme-gtk yaru-theme-icon && \
    rm -rf /var/lib/apt/lists/*
```

**PyCharm Community (latest via JetBrains API, pinnable):**
```dockerfile
ARG PYCHARM_VERSION=""
RUN set -eux; \
    url="$(curl -fsSL 'https://data.services.jetbrains.com/products/releases?code=PCC&latest=true&type=release' | jq -r '.PCC[0].downloads.linux.link')"; \
    if [ -n "$PYCHARM_VERSION" ]; then url="https://download.jetbrains.com/python/pycharm-community-${PYCHARM_VERSION}.tar.gz"; fi; \
    curl -fsSL "$url" -o /tmp/pycharm.tar.gz; \
    mkdir -p /opt/pycharm; \
    tar -xzf /tmp/pycharm.tar.gz -C /opt/pycharm --strip-components=1; \
    rm /tmp/pycharm.tar.gz; \
    ln -sf /opt/pycharm/bin/pycharm.sh /usr/local/bin/pycharm
COPY root/defaults/applications/pycharm.desktop /usr/share/applications/pycharm.desktop
```

(JetBrains tarball bundles its own JBR runtime — no separate JDK needed.)

### New file: `root/defaults/applications/pycharm.desktop`
```ini
[Desktop Entry]
Type=Application
Name=PyCharm Community
Icon=/opt/pycharm/bin/pycharm.svg
Exec=/opt/pycharm/bin/pycharm.sh %f
Categories=Development;IDE;
Terminal=false
StartupWMClass=jetbrains-pycharm-ce
```

### Theme: `xsettings.xml`
Change `Net/ThemeName` `Adwaita-dark` → `Yaru-dark`, `Net/IconThemeName` `Adwaita` → `Yaru-dark`. Seeded into `/config/.config/xfce4` on first run by the existing startup-script copy.

### Templates: repoint `dev-desktop.json`, delete `xfce-desktop.json`
Current reality: `images/desktop/` builds `selkies-desktop:latest`; **`xfce-desktop.json`** points at it, while **`dev-desktop.json`** points at the raw `baseimage-selkies:debiantrixie` (no custom build → no dev tools). Decision: **repoint `dev-desktop.json`** —
- Repoint `dev-desktop.json` → `image: selkies-desktop:latest`; make it the dev-workstation template (description/tags: VSCode, PyCharm, Node, Python, btop, nano, Yaru-dark; `internal_port` 3000 to match the built image; align `gpu_enabled`/limits with workstation needs).
- **Keep `xfce-desktop.json`** as the generic full-XFCE template (also points at `selkies-desktop:latest` — same image, different framing: generic desktop vs. dev workstation).

Seeding reads the templates dir dynamically and tests use isolated payloads, so editing a template JSON breaks no backend tests.

## Out of Scope

- Office, email, media-player software (explicitly excluded).
- New/separate image (decision: extend existing).
- Removing existing XFCE utilities (`ristretto`, `mousepad`) — tiny, removal risks the goodies metapackage; left in place.
- GNOME Shell (see Context).
- The dead `images/gnome-desktop/` dir — to be removed in implementation cleanup.

## Validation

Image-build artifact; staged build → run → inspect:

1. **Build:** `cd images/desktop && make build` — succeeds, no snapd.
2. **Binaries:** `docker run --rm selkies-desktop:latest bash -lc 'for b in node npm code pycharm nano btop htop git python3 curl google-chrome firefox; do command -v $b && echo OK $b || echo MISSING $b; done'` — all OK.
3. **PyCharm:** confirm `/opt/pycharm/bin/pycharm.sh` exists and `.desktop` installed.
4. **Theme:** confirm `xsettings.xml` shipped with `Yaru-dark`.
5. **Visual (human):** run container, open `localhost:3000`, confirm dark XFCE desktop, launch VSCode + PyCharm + Chrome + Firefox from menu.

## Open Questions (resolve at implementation)

- Node 22 vs current LTS at build time — pin to 22 for determinism unless newer LTS preferred.
- Whether to also drop `ristretto`/`mousepad` for strict "no fluff" — left in by default.
</content>
