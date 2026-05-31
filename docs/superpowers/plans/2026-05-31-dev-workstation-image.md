# Dev Workstation Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing XFCE Selkies image (`images/desktop/`, builds `selkies-desktop:latest`) into a lean developer workstation — add Node/npm, VSCode, PyCharm Community, nano, btop, and a Yaru dark theme — then surface it via the `dev-desktop` Hub template.

**Architecture:** Append new install layers to the existing `images/desktop/Dockerfile` after the current "Development Tools" layer; existing layers (XFCE, Firefox, Chrome, zsh, python, git, uv, htop) are untouched. Switch the seeded XFCE theme from `Adwaita-dark` to `Yaru-dark` via `xsettings.xml`. Repoint `templates/dev-desktop.json` at the built image. Remove the abandoned `images/gnome-desktop/` tree.

**Tech Stack:** Docker, `ghcr.io/linuxserver/baseimage-selkies:ubunturesolute`, XFCE (Wayland via labwc) + Selkies/Pixelflux, NodeSource (Node 22), Microsoft apt repo (VSCode `code`), JetBrains tarball (PyCharm Community), Yaru theme, FastAPI template seeding (JSON).

**Validation note:** Image-build artifact. The loop is **build → run container → inspect**, not pytest. No backend code changes; template seeding reads the dir dynamically and existing tests use isolated payloads, so editing `dev-desktop.json` and deleting a directory break nothing. Each Dockerfile task ends by building to keep layers green.

**Prereq for build/run tasks:** Docker available; ports 3000/3001 free; browser at `http://localhost:3000` for the human visual check. `make` targets run from `images/desktop/`.

---

## File Structure

- `images/desktop/Dockerfile` — add Node, VSCode, PyCharm, nano+btop+Yaru layers (after line ~76, before the UV layer).
- `images/desktop/root/defaults/applications/pycharm.desktop` — new launcher entry for PyCharm (copied to `/usr/share/applications/`).
- `images/desktop/root/defaults/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml` — theme `Adwaita-dark` → `Yaru-dark`.
- `templates/dev-desktop.json` — repoint image, refresh metadata.
- `images/gnome-desktop/` — delete (abandoned).

---

## Task 1: Add Node.js + npm

**Files:**
- Modify: `images/desktop/Dockerfile` (insert after the "Development Tools" `RUN` block, currently ending `jq \ && rm -rf /var/lib/apt/lists/*`)

- [ ] **Step 1: Insert Node layer**

Add immediately after the Development Tools `RUN` block (after the line `    && rm -rf /var/lib/apt/lists/*` that follows `jq \`):

```dockerfile
# ─── Node.js 22 + npm (NodeSource deb, not snap) ─────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Build to verify the layer**

Run: `cd images/desktop && docker build -t selkies-desktop:latest .`
Expected: build succeeds through the Node layer.

- [ ] **Step 3: Verify node + npm present**

Run: `docker run --rm selkies-desktop:latest bash -lc 'node --version && npm --version'`
Expected: prints a `v22.x` line and an npm version, exit 0.

- [ ] **Step 4: Commit**

```bash
git add images/desktop/Dockerfile
git commit -m "feat(image): add Node.js 22 + npm to dev workstation"
```

---

## Task 2: Add VSCode

**Files:**
- Modify: `images/desktop/Dockerfile` (insert after the Node layer from Task 1)

- [ ] **Step 1: Insert VSCode layer**

Add after the Node layer:

```dockerfile
# ─── VSCode (Microsoft apt repo, deb) ────────────────────────────────────────
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list && \
    apt-get update && apt-get install -y --no-install-recommends code && \
    rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Build**

Run: `cd images/desktop && docker build -t selkies-desktop:latest .`
Expected: build succeeds through the VSCode layer.

- [ ] **Step 3: Verify code binary + desktop entry**

Run: `docker run --rm selkies-desktop:latest bash -lc 'command -v code && ls /usr/share/applications/code.desktop'`
Expected: prints `/usr/bin/code` and the `.desktop` path, exit 0.

- [ ] **Step 4: Commit**

```bash
git add images/desktop/Dockerfile
git commit -m "feat(image): add VSCode to dev workstation"
```

---

## Task 3: Add nano, btop, and Yaru theme packages

**Files:**
- Modify: `images/desktop/Dockerfile` (insert after the VSCode layer)

- [ ] **Step 1: Insert utilities + theme layer**

Add after the VSCode layer:

```dockerfile
# ─── CLI utils + Yaru dark theme ─────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano \
    btop \
    yaru-theme-gtk \
    yaru-theme-icon \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 2: Build**

Run: `cd images/desktop && docker build -t selkies-desktop:latest .`
Expected: build succeeds.

- [ ] **Step 3: Verify binaries + theme dir**

Run: `docker run --rm selkies-desktop:latest bash -lc 'command -v nano btop && ls -d /usr/share/themes/Yaru-dark'`
Expected: prints `/usr/bin/nano`, `/usr/bin/btop`, and the `Yaru-dark` theme directory, exit 0.

- [ ] **Step 4: Commit**

```bash
git add images/desktop/Dockerfile
git commit -m "feat(image): add nano, btop, and Yaru theme packages"
```

---

## Task 4: Add PyCharm Community

**Files:**
- Create: `images/desktop/root/defaults/applications/pycharm.desktop`
- Modify: `images/desktop/Dockerfile` (insert after the utils+theme layer)

- [ ] **Step 1: Create the PyCharm desktop launcher**

Create `images/desktop/root/defaults/applications/pycharm.desktop`:

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

- [ ] **Step 2: Insert PyCharm install layer**

Add after the utils+theme layer (`jq` is already installed earlier, so the JSON API parse works):

```dockerfile
# ─── PyCharm Community (JetBrains tarball, bundles JBR runtime) ───────────────
RUN set -eux; \
    url="$(curl -fsSL 'https://data.services.jetbrains.com/products/releases?code=PCC&latest=true&type=release' | jq -r '.PCC[0].downloads.linux.link')"; \
    curl -fsSL "$url" -o /tmp/pycharm.tar.gz; \
    mkdir -p /opt/pycharm; \
    tar -xzf /tmp/pycharm.tar.gz -C /opt/pycharm --strip-components=1; \
    rm /tmp/pycharm.tar.gz; \
    ln -sf /opt/pycharm/bin/pycharm.sh /usr/local/bin/pycharm
COPY root/defaults/applications/pycharm.desktop /usr/share/applications/pycharm.desktop
```

- [ ] **Step 3: Build**

Run: `cd images/desktop && docker build -t selkies-desktop:latest .`
Expected: build succeeds; the JetBrains URL resolves and the tarball extracts.

- [ ] **Step 4: Verify PyCharm install + launcher**

Run: `docker run --rm selkies-desktop:latest bash -lc 'ls /opt/pycharm/bin/pycharm.sh && command -v pycharm && ls /usr/share/applications/pycharm.desktop'`
Expected: prints the pycharm.sh path, `/usr/local/bin/pycharm`, and the `.desktop` path, exit 0.

- [ ] **Step 5: Commit**

```bash
git add images/desktop/Dockerfile images/desktop/root/defaults/applications/pycharm.desktop
git commit -m "feat(image): add PyCharm Community to dev workstation"
```

---

## Task 5: Switch seeded theme to Yaru-dark

**Files:**
- Modify: `images/desktop/root/defaults/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml`

- [ ] **Step 1: Edit the theme properties**

In `xsettings.xml`, change the two theme lines:

From:
```xml
    <property name="ThemeName" type="string" value="Adwaita-dark"/>
    <property name="IconThemeName" type="string" value="Adwaita"/>
```
To:
```xml
    <property name="ThemeName" type="string" value="Yaru-dark"/>
    <property name="IconThemeName" type="string" value="Yaru-dark"/>
```

(Leave `CursorThemeName`, `CursorSize`, the `Gtk` font block, and the `Xft` block unchanged.)

- [ ] **Step 2: Validate the XML**

Run: `python3 -c "import xml.dom.minidom,sys; xml.dom.minidom.parse('images/desktop/root/defaults/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml'); print('XML OK')"`
Expected: prints `XML OK`.

- [ ] **Step 3: Confirm new values present**

Run: `grep -E 'Yaru-dark' images/desktop/root/defaults/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml`
Expected: two matching lines (ThemeName + IconThemeName).

- [ ] **Step 4: Commit**

```bash
git add images/desktop/root/defaults/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml
git commit -m "feat(image): default XFCE to Yaru-dark theme"
```

---

## Task 6: Repoint the dev-desktop Hub template

**Files:**
- Modify: `templates/dev-desktop.json`

- [ ] **Step 1: Replace template contents**

Overwrite `templates/dev-desktop.json` with (repointed image, port 3000 to match the built image, refreshed metadata; note `selkies-desktop:latest` exposes 3000):

```json
{
  "name": "dev-desktop",
  "display_name": "Developer Workstation",
  "image": "selkies-desktop:latest",
  "icon": "🛠️",
  "description": "XFCE dev workstation — VSCode, PyCharm, Node, Python, git, Firefox, Chrome, btop, dark theme",
  "env_vars": {
    "PUID": "1000",
    "PGID": "1000",
    "PIXELFLUX_WAYLAND": "true",
    "TITLE": "Developer Workstation"
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
  "category": "development",
  "tags": ["development", "coding", "vscode", "pycharm", "xfce"],
  "session_config": {
    "idle_timeout": "60m",
    "grace_period": "10m",
    "timeout_action": "stop",
    "never_timeout": false,
    "max_session_duration": null
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `python3 -c "import json; d=json.load(open('templates/dev-desktop.json')); print('OK', d['name'], d['image'], d['internal_port'])"`
Expected: prints `OK dev-desktop selkies-desktop:latest 3000`.

- [ ] **Step 3: Backend tests still green**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all tests pass (template change does not affect isolated-payload tests).

- [ ] **Step 4: Commit**

```bash
git add templates/dev-desktop.json
git commit -m "feat(templates): repoint dev-desktop at built dev workstation image"
```

---

## Task 7: Remove the abandoned GNOME image tree

**Files:**
- Delete: `images/gnome-desktop/` (entire directory)

- [ ] **Step 1: Remove the directory**

Run: `git rm -r images/gnome-desktop`
Expected: git stages deletions for all files under `images/gnome-desktop/`.

- [ ] **Step 2: Confirm removal**

Run: `ls images/gnome-desktop 2>&1 | head -1`
Expected: `ls: cannot access 'images/gnome-desktop': No such file or directory`.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove abandoned GNOME desktop image (blocked by no-systemd base)"
```

---

## Task 8: Full image verification + end-to-end

**Files:** (none — verification only)

- [ ] **Step 1: Clean rebuild**

Run: `cd images/desktop && make clean && make build`
Expected: image builds from scratch, no errors, no snapd pulled.

- [ ] **Step 2: All tools present**

Run:
```bash
docker run --rm selkies-desktop:latest bash -lc 'for b in node npm code pycharm nano btop htop git python3 curl google-chrome firefox uv tmux; do command -v $b >/dev/null && echo "OK $b" || echo "MISSING $b"; done'
```
Expected: every line `OK <tool>`, none `MISSING`.

- [ ] **Step 3: No fluff present (sanity)**

Run: `docker run --rm selkies-desktop:latest bash -lc 'for b in libreoffice thunderbird; do command -v $b >/dev/null && echo "FOUND $b" || echo "absent $b"; done'`
Expected: both `absent` (no office/email pulled in).

- [ ] **Step 4: Human visual check**

Run: `cd images/desktop && make run`, open `http://localhost:3000`.
Expected: dark (Yaru-dark) XFCE desktop loads. From the menu, launch VSCode, PyCharm Community, Chrome, Firefox — each opens. `btop` runs in a terminal.

- [ ] **Step 5: Tear down**

Run: `cd images/desktop && make stop`
Expected: container stops cleanly.

---

## Self-Review

**Spec coverage:**
- Extend existing `images/desktop/` → Tasks 1–5 (no new image). ✓
- Node/npm → T1; VSCode → T2; nano/btop/Yaru pkgs → T3; PyCharm Community → T4; dark theme → T5. ✓
- Firefox/Chrome/Python/git/curl/htop already present → unchanged, verified in T8 Step 2. ✓
- No fluff (no office/email/media) → none added; T8 Step 3 sanity-checks absence. ✓
- No snaps → all deb/tarball; T8 Step 1 notes no snapd. ✓
- Repoint `dev-desktop.json`, keep `xfce-desktop.json` → T6 (xfce-desktop.json untouched). ✓
- Remove dead `images/gnome-desktop/` → T7. ✓
- Validation staged build→run→inspect → each task builds; T8 end-to-end. ✓

**Placeholder scan:** No TBD/TODO. Every code step has concrete content; every run step has exact command + expected output. PyCharm version uses the JetBrains "latest release" API (deterministic at build time, no manual version string). ✓

**Type/identity consistency:** `selkies-desktop:latest` (built image) used consistently in T6 + verified in T8; `/opt/pycharm` + `pycharm.sh` + `/usr/local/bin/pycharm` + `StartupWMClass=jetbrains-pycharm-ce` consistent between T4 Dockerfile and `pycharm.desktop`; `Yaru-dark` consistent between T3 (package `yaru-theme-gtk` provides `/usr/share/themes/Yaru-dark`) and T5 (xsettings value). Insertion order chained: each Dockerfile task says "after the previous layer." ✓

**Note:** `dev-desktop.json` gains `PIXELFLUX_WAYLAND=true` + port 3000 to match how `selkies-desktop:latest` runs (the old dev-desktop used raw base + port 3001); this aligns it with `xfce-desktop.json`'s proven config.
</content>
