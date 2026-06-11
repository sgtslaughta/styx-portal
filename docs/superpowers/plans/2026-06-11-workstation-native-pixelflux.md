# Workstation Streaming v2 — Native pixelflux Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failed selkies-gstreamer tarball engine in the workstation agent with the native selkies 2.x + pixelflux/pcmflux stack (websocket, GPU encode, X11 mirror + Wayland second-seat), keeping the proven enrollment/routing chain.

**Architecture:** The agent becomes a venv install (system python ≥3.10, prebuilt wheels served LAN-only from the portal's artifact cache). A small aiohttp *gateway* serves the vendored web dashboard and proxies `/websocket` with basic auth on the workstation port (8443); selkies itself is forced to loopback. Two modes chosen at enroll time: `mirror` (attach to live X display, resolution locked) and `seat` (pixelflux Wayland compositor + nested labwc + host apps). A ~1 MB lib shim (libva 2.22, libwayland-server 1.23) makes pixelflux 1.6.4 work on Ubuntu 24.04-era distros.

**Tech Stack:** Python 3.10+ stdlib agent + aiohttp gateway; selkies 2.x (pinned commit `0d134b6e1ffe42a579bc66363b0e7159ab22aacc`); pixelflux 1.6.4; pcmflux 1.0.8; FastAPI backend; bash enroll script.

**Spec:** `docs/superpowers/specs/2026-06-11-workstation-native-pixelflux-design.md` (read it first — esp. "Spike results" for protocol facts and the libva floor).

**Test commands:**
- Backend: `cd backend && .venv/bin/python -m pytest -v`
- Agent: `cd backend && .venv/bin/python -m pytest ../agent/tests -v`
- Lint: `cd backend && .venv/bin/python -m ruff check app/ tests/`

**Verified facts you must not "fix":**
- selkies has NO PyPI 2.x release; install from the pinned GitHub tarball. PyPI `selkies` 1.6.1 is the WRONG (legacy) package.
- selkies needs `setuptools` at runtime on py3.12 (GPUtil imports `distutils`).
- The selkies data websocket hardcodes bind `0.0.0.0` — the launcher monkeypatch (Task 7) is deliberate, not a hack to remove.
- `display=1024x768` in selkies' init log is a placeholder, not the capture size.
- ws protocol: path `/websocket`; client sends `SETTINGS,{json}` then `START_VIDEO`/`START_AUDIO`.

---

### Task 1: Amend spec — install prefix

`/opt/styx-agent` (spec §Install layout) needs sudo to create AND to remove; sudo-less removal is a core goal. Keep the proven v1 layout instead.

**Files:**
- Modify: `docs/superpowers/specs/2026-06-11-workstation-native-pixelflux-design.md`

- [ ] **Step 1: Replace the install-layout section**

Find the block starting `/opt/styx-agent/` (code fence) through `chowned to the enrolling user.` and replace with:

```markdown
~/.local/share/styx-agent/
  venv/            system python3 venv (pixelflux, pcmflux, selkies, aiohttp…)
  web/             dashboard dist
  lib/             shim libs (libva.so.2, libva-drm.so.2, libwayland-server.so.0)
  logs/
~/.config/styx-agent/config.json   (0600)
```
systemd user unit `styx-agent.service` (existing v1 pattern). Removal =
stop+disable unit, `rm -rf ~/.local/share/styx-agent ~/.config/styx-agent`,
deregister — **no sudo required** (amended from /opt: sudo-less removal is a
core goal; /opt would need sudo to create and to remove).

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-06-11-workstation-native-pixelflux-design.md
git commit -m "docs(spec): amend install prefix to ~/.local/share (sudo-less removal)"
```

---

### Task 2: Backend config — replace tarball URL with pinned app URL

**Files:**
- Modify: `backend/app/config.py:43-46`

- [ ] **Step 1: Replace the setting**

Replace:

```python
    SELKIES_TARBALL_URL: str = (
        "https://github.com/selkies-project/selkies-gstreamer/releases/download/"
        "v1.6.2/selkies-gstreamer-portable-v1.6.2_amd64.tar.gz"
    )
```

with:

```python
    # selkies 2.x has no PyPI release; pin the exact commit linuxserver builds.
    SELKIES_APP_URL: str = (
        "https://github.com/selkies-project/selkies/archive/"
        "0d134b6e1ffe42a579bc66363b0e7159ab22aacc.tar.gz"
    )
```

- [ ] **Step 2: Find all other references (they are fixed in Tasks 3–4)**

Run: `grep -rn "SELKIES_TARBALL_URL\|ensure_selkies_tarball" backend/ agent/`
Expected hits: `backend/app/services/artifacts.py`, `backend/app/routers/enroll.py`, `backend/tests/test_artifacts.py`, `agent/enroll.sh`. Do NOT commit yet — Task 3 makes the tree consistent.

---

### Task 3: Generic artifact service

One service for all agent artifacts. URL-backed artifacts download on first request; build artifacts (wheelhouse, web dist, shim) must be pre-placed by `scripts/build_agent_artifacts.sh` (Task 5).

**Files:**
- Rewrite: `backend/app/services/artifacts.py`
- Rewrite: `backend/tests/test_artifacts.py`

- [ ] **Step 1: Write the failing tests** (full file replacement)

```python
import pytest

from app.services import artifacts


@pytest.mark.asyncio
async def test_url_artifact_cached_file_is_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies-app.tar.gz").write_bytes(b"cached")
    path = await artifacts.ensure_artifact("selkies-app.tar.gz")
    assert path.read_bytes() == b"cached"


@pytest.mark.asyncio
async def test_url_artifact_downloads_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))

    async def fake_download(url, dest):
        dest.write_bytes(b"downloaded:" + url.encode())

    monkeypatch.setattr(artifacts, "_download", fake_download)
    path = await artifacts.ensure_artifact("selkies-app.tar.gz")
    assert path.read_bytes().startswith(b"downloaded:https://github.com/")


@pytest.mark.asyncio
async def test_prebuilt_artifact_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    with pytest.raises(artifacts.ArtifactMissing) as e:
        await artifacts.ensure_artifact("wheelhouse-x86_64.tar.gz")
    assert "build_agent_artifacts" in str(e.value)


@pytest.mark.asyncio
async def test_prebuilt_artifact_served_when_placed(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies-web.tar.gz").write_bytes(b"web")
    path = await artifacts.ensure_artifact("selkies-web.tar.gz")
    assert path.read_bytes() == b"web"


@pytest.mark.asyncio
async def test_unknown_artifact_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    with pytest.raises(artifacts.ArtifactMissing):
        await artifacts.ensure_artifact("../../etc/passwd")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_artifacts.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'ensure_artifact'`

- [ ] **Step 3: Rewrite the service** (full file replacement)

```python
"""Agent artifact cache, served LAN-only to enrolling workstations.

Two kinds of artifacts:
- URL-backed: downloaded once from a pinned upstream URL, then cached.
- Prebuilt:   produced by scripts/build_agent_artifacts.sh on the server
  host and pre-placed in ARTIFACT_CACHE_DIR (wheels need a manylinux build
  env; the web dist is extracted from the linuxserver image). Never
  downloaded here.
"""
import asyncio
from pathlib import Path

import httpx

from app.config import Settings

_settings = Settings()
_lock = asyncio.Lock()

# name -> upstream URL (None = prebuilt, must be pre-placed)
ARTIFACTS: dict[str, str | None] = {
    "selkies-app.tar.gz": _settings.SELKIES_APP_URL,
    "wheelhouse-x86_64.tar.gz": None,
    "selkies-web.tar.gz": None,
    "libshim-x86_64.tar.gz": None,
}


class ArtifactMissing(Exception):
    pass


async def _download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)


async def ensure_artifact(name: str) -> Path:
    if name not in ARTIFACTS:
        raise ArtifactMissing(f"Unknown artifact: {name!r}")
    dest = Path(_settings.ARTIFACT_CACHE_DIR) / name
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    url = ARTIFACTS[name]
    if url is None:
        raise ArtifactMissing(
            f"{name} not found in {_settings.ARTIFACT_CACHE_DIR}. Run "
            "scripts/build_agent_artifacts.sh on the server host to build it.")
    async with _lock:
        if dest.is_file() and dest.stat().st_size > 0:  # re-check under lock
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        try:
            await _download(url, tmp)
            tmp.rename(dest)
        finally:
            tmp.unlink(missing_ok=True)
    return dest
```

Note: `ARTIFACTS` snapshot of `SELKIES_APP_URL` is fine — settings are env-driven and static per process. The fake-download test asserts the URL flows through.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_artifacts.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/services/artifacts.py backend/tests/test_artifacts.py
git commit -m "feat(backend): generic agent-artifact cache (selkies app, wheelhouse, web, libshim)"
```

(Backend won't import-clean until Task 4 fixes the router — run only `tests/test_artifacts.py` here.)

---

### Task 4: Enroll router — parameterized artifacts + new agent files

**Files:**
- Modify: `backend/app/routers/enroll.py:50-73`
- Modify: `backend/tests/test_workstation_enroll.py` (additions)

- [ ] **Step 1: Write failing tests** (append to `backend/tests/test_workstation_enroll.py`; reuse that file's existing `client` fixture — read its imports first and match them)

```python
async def test_artifact_endpoint_serves_prebuilt(client, tmp_path, monkeypatch):
    from app.services import artifacts
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies-web.tar.gz").write_bytes(b"web-dist")
    r = await client.get("/api/enroll/artifacts/selkies-web.tar.gz")
    assert r.status_code == 200
    assert r.content == b"web-dist"


async def test_artifact_endpoint_unknown_name_404(client):
    r = await client.get("/api/enroll/artifacts/evil.tar.gz")
    assert r.status_code == 404


async def test_artifact_endpoint_missing_prebuilt_503(client, tmp_path, monkeypatch):
    from app.services import artifacts
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    r = await client.get("/api/enroll/artifacts/wheelhouse-x86_64.tar.gz")
    assert r.status_code == 503
    assert "build_agent_artifacts" in r.json()["detail"]


async def test_agent_file_endpoints_served(client):
    for name in ("agent.py", "engine.py", "gateway.py", "selkies_launcher.py",
                 "uninstall"):
        r = await client.get(f"/api/enroll/{name}")
        assert r.status_code == 200, name
```

If the existing tests in that file are sync (TestClient), write these in the same style — match the file's conventions exactly.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/python -m pytest tests/test_workstation_enroll.py -v -k artifact`
Expected: FAIL (404s / import errors)

- [ ] **Step 3: Replace the artifact + file endpoints in `enroll.py`**

Replace the `/agent.py`, `/uninstall`, and `/artifacts/selkies.tar.gz` route functions (keep `/script` and `_serve` as-is) with:

```python
@router.get("/agent.py")
async def agent_py():
    return _serve("styx_agent.py")


@router.get("/engine.py")
async def engine_py():
    return _serve("engine.py")


@router.get("/gateway.py")
async def gateway_py():
    return _serve("gateway.py")


@router.get("/selkies_launcher.py")
async def selkies_launcher_py():
    return _serve("selkies_launcher.py")


@router.get("/uninstall")
async def uninstall_script():
    return _serve("uninstall.sh")


@router.get("/artifacts/{name}")
async def artifact(name: str):
    from app.services.artifacts import ARTIFACTS, ArtifactMissing, ensure_artifact
    if name not in ARTIFACTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such artifact: {name}")
    try:
        path = await ensure_artifact(name)
    except ArtifactMissing as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except Exception as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Artifact {name} unavailable ({e.__class__.__name__}). "
            "Check network or pre-place it in the artifact cache.")
    return FileResponse(path, media_type="application/gzip", filename=name)
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: all PASS (fix any test still referencing `SELKIES_TARBALL_URL` or the old route by updating it to the new names — `grep -rn "selkies.tar.gz\|SELKIES_TARBALL_URL" backend/tests/`).

- [ ] **Step 5: Lint + commit**

```bash
cd backend && .venv/bin/python -m ruff check app/ tests/
git add backend/app/routers/enroll.py backend/tests/test_workstation_enroll.py
git commit -m "feat(backend): parameterized artifact endpoint + new agent file routes"
```

---

### Task 5: Artifact builder script (server host)

Builds the three prebuilt artifacts into the artifact cache. Runs on the PORTAL host (needs docker + curl), not on workstations.

**Files:**
- Create: `scripts/build_agent_artifacts.sh`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Build the prebuilt agent artifacts into the portal's artifact cache.
# Run on the portal server host (needs docker + curl). Re-run to refresh.
# Usage: scripts/build_agent_artifacts.sh [output-dir]   (default ./data/artifacts)
set -euo pipefail

OUT="${1:-./data/artifacts}"
mkdir -p "$OUT"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

SELKIES_COMMIT="0d134b6e1ffe42a579bc66363b0e7159ab22aacc"
SELKIES_URL="https://github.com/selkies-project/selkies/archive/${SELKIES_COMMIT}.tar.gz"
MANYLINUX_IMG="quay.io/pypa/manylinux_2_34_x86_64"
SELKIES_BASEIMAGE="ghcr.io/linuxserver/baseimage-selkies:debiantrixie"
UBU="http://archive.ubuntu.com/ubuntu/pool/main"

echo "==> [1/3] wheelhouse-x86_64.tar.gz (wheels for cp310-cp313)"
# Build/collect every wheel the agent venv needs, per python minor version.
# xkbcommon is source-only on PyPI -> built here so workstations never compile.
docker run --rm -v "$WORK:/out" "$MANYLINUX_IMG" bash -ec '
  yum install -y -q libxkbcommon-devel
  for PY in cp310-cp310 cp311-cp311 cp312-cp312 cp313-cp313; do
    PIP="/opt/python/$PY/bin/pip"
    "$PIP" -q wheel --wheel-dir /out/wheelhouse \
      "'"$SELKIES_URL"'" pixelflux==1.6.4 pcmflux==1.0.8 \
      setuptools aiohttp pulsectl
  done
'
tar -C "$WORK" -czf "$OUT/wheelhouse-x86_64.tar.gz" wheelhouse
echo "    $(ls "$WORK/wheelhouse" | wc -l) wheels"

echo "==> [2/3] selkies-web.tar.gz (dashboard dist from linuxserver image)"
docker pull -q "$SELKIES_BASEIMAGE"
CID=$(docker create "$SELKIES_BASEIMAGE")
docker cp "$CID:/usr/share/selkies/web" "$WORK/web"
docker rm -f "$CID" >/dev/null
tar -C "$WORK" -czf "$OUT/selkies-web.tar.gz" web

echo "==> [3/3] libshim-x86_64.tar.gz (libva 2.22 + libwayland-server 1.23)"
mkdir -p "$WORK/shim/lib"
for deb in \
  "libv/libva/libva2_2.22.0-3ubuntu3_amd64.deb" \
  "libv/libva/libva-drm2_2.22.0-3ubuntu3_amd64.deb" \
  "w/wayland/libwayland-server0_1.23.1-3_amd64.deb"; do
  curl -fsSL "$UBU/$deb" -o "$WORK/shim/pkg.deb"
  (cd "$WORK/shim" && ar x pkg.deb \
    && { tar xf data.tar.zst 2>/dev/null || tar xf data.tar.xz; } \
    && cp -a usr/lib/x86_64-linux-gnu/*.so.* lib/ \
    && rm -rf usr control.tar.* data.tar.* debian-binary pkg.deb)
done
tar -C "$WORK/shim" -czf "$OUT/libshim-x86_64.tar.gz" lib

echo "Done. Artifacts in $OUT:"
ls -lh "$OUT"/wheelhouse-x86_64.tar.gz "$OUT"/selkies-web.tar.gz "$OUT"/libshim-x86_64.tar.gz
```

- [ ] **Step 2: Make executable and smoke-test on this host**

Run: `chmod +x scripts/build_agent_artifacts.sh && ./scripts/build_agent_artifacts.sh /tmp/artifact-test`
Expected: three tarballs listed. (Takes minutes — docker pulls. If the manylinux pip-wheel step fails for a python version, note which and continue; cp312 must succeed.)
Then: `tar tzf /tmp/artifact-test/wheelhouse-x86_64.tar.gz | grep -c '\.whl'` → > 20.

- [ ] **Step 3: Commit**

```bash
git add scripts/build_agent_artifacts.sh
git commit -m "feat(scripts): build agent artifacts (wheelhouse, web dist, libshim)"
```

---

### Task 6: agent/engine.py — mode logic, selkies command, helpers

Pure functions, fully unit-testable. The supervisor (Task 9) calls these.

**Files:**
- Create: `agent/engine.py`
- Create: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine  # noqa: E402


def _cfg(tmp_path, **kw):
    install = tmp_path / "styx-agent"
    (install / "venv/bin").mkdir(parents=True)
    (install / "lib").mkdir()
    (install / "web").mkdir()
    cfg = {
        "server": "https://192.168.1.10", "agent_token": "tok",
        "workstation_id": "ws1", "port": 8443,
        "selkies_user": "styx", "selkies_password": "pw",
        "mode": "mirror", "display": ":1",
        "stream_settings": {"framerate": 60},
        "install_dir": str(install),
        "ca_pin": "", "server_cert": "",
    }
    cfg.update(kw)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return cfg


def test_mirror_cmd_attaches_display_and_locks_resolution(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, xa: (2560, 1440))
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: "/tmp/xa")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "out.monitor")
    cmd, env = engine.build_selkies_cmd(cfg)
    assert cmd[0].endswith("venv/bin/python")
    assert cmd[1].endswith("selkies_launcher.py")
    assert "--port=8444" in cmd                      # internal ws = port+1
    assert "--is-manual-resolution-mode=true" in cmd
    assert "--manual-width=2560" in cmd and "--manual-height=1440" in cmd
    assert "--dri-node=/dev/dri/renderD128" in cmd
    assert "--audio-device-name=out.monitor" in cmd
    assert env["DISPLAY"] == ":1"
    assert env["XAUTHORITY"] == "/tmp/xa"
    assert "PIXELFLUX_WAYLAND" not in env
    assert env["LD_LIBRARY_PATH"].startswith(cfg["install_dir"] + "/lib")
    assert env["PYTHONNOUSERSITE"] == "1"
    # secrets never in argv
    assert not any("pw" in a for a in cmd)


def test_seat_cmd_uses_wayland_backend(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "styx-seat.monitor")
    cmd, env = engine.build_selkies_cmd(cfg)
    assert env["PIXELFLUX_WAYLAND"] == "true"
    assert env["DRINODE"] == "/dev/dri/renderD128"
    assert "DISPLAY" not in env
    assert "--is-manual-resolution-mode=true" not in cmd


def test_seat_cmd_without_gpu_falls_back_to_cpu(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "styx-seat.monitor")
    cmd, env = engine.build_selkies_cmd(cfg)
    assert "DRINODE" not in env
    assert not any(a.startswith("--dri-node") for a in cmd)


def test_audio_disabled_when_no_pulse(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, xa: (1920, 1080))
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg)
    assert env["SELKIES_AUDIO_ENABLED"] == "false"


def test_wait_for_wayland_socket(tmp_path):
    before = set()
    (tmp_path / "wayland-1").touch()
    name = engine.wait_for_wayland_socket(str(tmp_path), before, timeout=1)
    assert name == "wayland-1"
    assert engine.wait_for_wayland_socket(str(tmp_path), {"wayland-1"}, timeout=0.2) is None


def test_pick_dri_node(tmp_path, monkeypatch):
    dri = tmp_path / "dri"
    dri.mkdir()
    (dri / "renderD128").touch()
    monkeypatch.setattr(engine, "DRI_DIR", str(dri))
    assert engine.pick_dri_node().endswith("renderD128")
    monkeypatch.setattr(engine, "DRI_DIR", str(tmp_path / "nope"))
    assert engine.pick_dri_node() == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests/test_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine'`

- [ ] **Step 3: Implement `agent/engine.py`**

```python
"""Engine logic for the pixelflux/selkies 2.x agent — pure functions only.

mirror: attach to a live X display (XShm capture), resolution locked to the
        physical screen so selkies never xrandr-resizes the user's monitor.
seat:   pixelflux's own Wayland compositor; host apps join via WAYLAND_DISPLAY.
"""
import glob
import os
import time
from pathlib import Path

HOME = Path.home()
DRI_DIR = "/dev/dri"
INTERNAL_WS_OFFSET = 1     # selkies binds loopback on port+1; gateway owns port
SEAT_SINK = "styx-seat"    # null sink so seat audio never hits the speakers


def _find_xauthority(cfg: dict) -> str | None:
    """systemd --user starts with an empty env; resolve the cookie explicitly.
    Location varies by distro/display manager."""
    uid = os.getuid()
    candidates = [
        cfg.get("xauthority"),
        os.environ.get("XAUTHORITY"),
        str(HOME / ".Xauthority"),
        f"/run/user/{uid}/.mutter-Xwaylandauth",      # GNOME Xwayland
        f"/run/user/{uid}/gdm/Xauthority",            # GDM
    ]
    candidates += [str(p) for p in sorted(HOME.glob(".vnc/*Xauthority"))]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def pick_dri_node() -> str:
    nodes = sorted(glob.glob(os.path.join(DRI_DIR, "renderD*")))
    return nodes[0] if nodes else ""


def query_display_geometry(display: str, xauthority: str | None) -> tuple[int, int]:
    """Screen size of a live X display, via the venv's python-xlib."""
    from Xlib import display as xdisplay  # venv dep of selkies
    if xauthority:
        os.environ["XAUTHORITY"] = xauthority
    d = xdisplay.Display(display)
    try:
        s = d.screen()
        return s.width_in_pixels, s.height_in_pixels
    finally:
        d.close()


def resolve_monitor_source() -> str:
    """Monitor source of the default sink ('' = no audio server -> disable).
    selkies' baked-in default 'output.monitor' only exists in containers."""
    try:
        import pulsectl
        with pulsectl.Pulse("styx-agent") as p:
            return p.server_info().default_sink_name + ".monitor"
    except Exception:
        return ""


def ensure_seat_sink() -> str:
    """Create (idempotently) a null sink for seat audio; returns its monitor."""
    import pulsectl
    with pulsectl.Pulse("styx-agent") as p:
        if not any(s.name == SEAT_SINK for s in p.sink_list()):
            p.module_load("module-null-sink",
                          f"sink_name={SEAT_SINK} "
                          f"sink_properties=device.description={SEAT_SINK}")
    return f"{SEAT_SINK}.monitor"


def wait_for_wayland_socket(runtime_dir: str, before: set[str],
                            timeout: float = 15) -> str | None:
    """The compositor picks the first free wayland-N; detect it by diffing."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        now = {p.name for p in Path(runtime_dir).glob("wayland-*")
               if not p.name.endswith(".lock")}
        new = now - before
        if new:
            return sorted(new)[0]
        time.sleep(0.2)
    return None


def build_selkies_cmd(cfg: dict) -> tuple[list[str], dict]:
    """argv + env for the selkies process (run through selkies_launcher.py,
    which forces a loopback bind). Secrets travel via env, never argv."""
    install = Path(cfg["install_dir"])
    s = cfg.get("stream_settings", {})
    internal_port = cfg["port"] + INTERNAL_WS_OFFSET

    env = {
        "HOME": str(HOME),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR",
                                          f"/run/user/{os.getuid()}"),
        "LD_LIBRARY_PATH": str(install / "lib"),   # libva/libwayland shim
        "PYTHONNOUSERSITE": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }

    cmd = [
        str(install / "venv/bin/python"),
        str(install / "selkies_launcher.py"),
        f"--port={internal_port}",
        f"--control-port={internal_port + 1}",
        "--encoder=x264enc",          # pixelflux switches to VAAPI/NVENC itself
        f"--framerate={s.get('framerate', 60)}",
        "--mode=websockets",
    ]

    dri = pick_dri_node()
    if dri:
        cmd.append(f"--dri-node={dri}")

    if cfg.get("mode") == "seat":
        env["PIXELFLUX_WAYLAND"] = "true"
        if dri:
            env["DRINODE"] = dri
        monitor = resolve_monitor_source()
    else:  # mirror
        env["DISPLAY"] = cfg["display"]
        xauth = _find_xauthority(cfg)
        if xauth:
            env["XAUTHORITY"] = xauth
        w, h = query_display_geometry(cfg["display"], xauth)
        cmd += ["--is-manual-resolution-mode=true",
                f"--manual-width={w}", f"--manual-height={h}"]
        monitor = resolve_monitor_source()

    if monitor:
        env["SELKIES_AUDIO_ENABLED"] = "true"
        cmd.append(f"--audio-device-name={monitor}")
    else:
        env["SELKIES_AUDIO_ENABLED"] = "false"

    return cmd, env
```

(Note: seat mode resolves the *default* monitor at first; the supervisor swaps to `ensure_seat_sink()` output before launch — Task 9 wires that, keeping this function side-effect-free for tests.)

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests/test_engine.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): pixelflux engine logic — mirror/seat command builder + helpers"
```

---

### Task 7: agent/selkies_launcher.py — loopback bind

selkies hardcodes `0.0.0.0` for its data websocket (verified in source, `run_server`). Unauthenticated desktop control must not face the LAN; only the authenticated gateway may.

**Files:**
- Create: `agent/selkies_launcher.py`
- Create: `agent/tests/test_selkies_launcher.py`

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import selkies_launcher  # noqa: E402


def test_patch_rewrites_wildcard_host_only():
    calls = []

    def fake_serve(handler, host, port, **kw):
        calls.append((host, port))
        return "server"

    patched = selkies_launcher._loopback_only(fake_serve)
    assert patched(None, "0.0.0.0", 8444) == "server"
    assert patched(None, "127.0.0.1", 9000) == "server"
    assert calls == [("127.0.0.1", 8444), ("127.0.0.1", 9000)]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests/test_selkies_launcher.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""Run selkies with every websocket server bound to loopback.

Upstream hardcodes '0.0.0.0' (selkies.py run_server). The LAN-facing port
is owned by gateway.py, which enforces basic auth; selkies itself must only
be reachable through it. Patching serve() at import time covers the data
websocket and any future listener uniformly.
"""
import functools
import sys


def _loopback_only(serve):
    @functools.wraps(serve)
    def wrapper(handler, host, port, **kw):
        return serve(handler, "127.0.0.1", port, **kw)
    return wrapper


def main() -> None:
    import websockets.asyncio.server as ws_async
    ws_async.serve = _loopback_only(ws_async.serve)
    # selkies also imports `from websockets import asyncio as ...` variants;
    # the module attribute above is the single shared object they all resolve.
    from selkies.__main__ import main as selkies_main
    sys.argv[0] = "selkies"
    selkies_main()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests/test_selkies_launcher.py -v`
Expected: PASS

- [ ] **Step 5: Live check the patch point against the real package** (uses the spike venv on this box)

Run: `grep -n "ws_async" /tmp/styx-spike/venv2/lib/python3.12/site-packages/selkies/selkies.py | head -3`
Expected: an import like `from websockets import asyncio as ws_async` or `import websockets.asyncio.server as ws_async`. If the import style differs, adjust `main()` so the patched attribute is the one selkies actually calls (`selkies.selkies.ws_async.serve = ...` after importing `selkies.selkies` is the fallback that always works — but patch BEFORE `ws_entrypoint` runs).
Then: `cd /tmp/styx-spike && cp ~/code/remote-access/agent/selkies_launcher.py . && DISPLAY=:200 SELKIES_AUDIO_ENABLED=false ./venv2/bin/python selkies_launcher.py --port 8092 --control-port 8093 --encoder x264enc & sleep 8 && ss -ltn | grep 8092`
Expected: `127.0.0.1:8092` (NOT `0.0.0.0:8092`). Needs Xvfb `:200` running (`Xvfb :200 -screen 0 1920x1080x24 &` if not). Kill with `pgrep -f "port 809[2]" | xargs -r kill`. Never use a kill pattern that appears verbatim in your own shell command line.

- [ ] **Step 6: Commit**

```bash
git add agent/selkies_launcher.py agent/tests/test_selkies_launcher.py
git commit -m "feat(agent): selkies launcher forcing loopback websocket bind"
```

---

### Task 8: agent/gateway.py — static + auth + websocket proxy

The only LAN-facing listener on the workstation. Serves the vendored dashboard, enforces basic auth (Traefik injects the credentials server-side; direct LAN access prompts), proxies `/websocket` to loopback selkies.

**Files:**
- Create: `agent/gateway.py`
- Create: `agent/tests/test_gateway.py`

- [ ] **Step 1: Add aiohttp to backend dev env (test dependency)**

Run: `cd backend && .venv/bin/pip install aiohttp && grep -n "aiohttp" pyproject.toml || true`
If absent from pyproject, add `"aiohttp>=3.9"` to the dev/test dependency list in `backend/pyproject.toml` (match the file's existing dependency-group syntax — read it first).

- [ ] **Step 2: Write the failing tests**

```python
import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")


def _basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def test_check_auth_accepts_valid_header():
    assert gateway.check_auth(_basic("styx", "pw"), "styx", "pw") is True


def test_check_auth_rejects_bad_password_and_garbage():
    assert gateway.check_auth(_basic("styx", "wrong"), "styx", "pw") is False
    assert gateway.check_auth("", "styx", "pw") is False
    assert gateway.check_auth("Bearer abc", "styx", "pw") is False
    assert gateway.check_auth("Basic !!notb64!!", "styx", "pw") is False


@pytest.mark.asyncio
async def test_app_serves_static_with_auth(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    (tmp_path / "index.html").write_text("<html>dash</html>")
    app = gateway.create_app(str(tmp_path), "styx", "pw", upstream_port=1)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        r = await client.get("/", headers={"Authorization": _basic("styx", "pw")})
        assert r.status == 200
        assert "dash" in await r.text()
        r = await client.get("/")
        assert r.status == 401
        assert r.headers["WWW-Authenticate"].startswith("Basic")
    finally:
        await client.close()
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests/test_gateway.py -v`
Expected: FAIL — no module `gateway` (importorskip raises only if aiohttp missing; gateway import error must surface as failure — if importorskip skips, the module name is wrong).

- [ ] **Step 4: Implement**

```python
#!/usr/bin/env python3
"""LAN-facing gateway: dashboard static files + authenticated ws proxy.

Mirrors the upstream container's nginx layout (/ -> web dist, /websocket ->
loopback selkies) so the stock dashboard works unmodified. Basic auth on
everything: Traefik injects the Authorization header for portal users;
direct LAN visits get a browser prompt.

Usage: venv/bin/python gateway.py <web_dir> <listen_port> <upstream_port>
Credentials via env: STYX_GW_USER / STYX_GW_PASSWORD (argv is world-readable).
"""
import base64
import hmac
import os
import sys

import aiohttp
from aiohttp import web

CHUNK = 2 ** 16


def check_auth(header: str, user: str, password: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        got = base64.b64decode(header[6:], validate=True).decode()
    except Exception:
        return False
    expected = f"{user}:{password}"
    return hmac.compare_digest(got.encode(), expected.encode())


def create_app(web_dir: str, user: str, password: str,
               upstream_port: int) -> web.Application:
    @web.middleware
    async def auth_mw(request, handler):
        if not check_auth(request.headers.get("Authorization", ""), user, password):
            return web.Response(
                status=401, headers={"WWW-Authenticate": 'Basic realm="styx"'})
        return await handler(request)

    async def ws_proxy(request):
        ws_server = web.WebSocketResponse(max_msg_size=0)
        await ws_server.prepare(request)
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                    f"ws://127.0.0.1:{upstream_port}{request.path}",
                    max_msg_size=0) as ws_client:

                async def pump(src, dst):
                    async for msg in src:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await dst.send_str(msg.data)
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            await dst.send_bytes(msg.data)
                        else:
                            break
                    await dst.close()

                import asyncio
                await asyncio.gather(pump(ws_server, ws_client),
                                     pump(ws_client, ws_server),
                                     return_exceptions=True)
        return ws_server

    async def index(_request):
        return web.FileResponse(os.path.join(web_dir, "index.html"))

    app = web.Application(middlewares=[auth_mw])
    app.router.add_get("/websocket", ws_proxy)
    app.router.add_get("/", index)
    app.router.add_static("/", web_dir)
    return app


def main() -> None:
    web_dir, listen_port, upstream_port = (
        sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    user = os.environ["STYX_GW_USER"]
    password = os.environ["STYX_GW_PASSWORD"]
    web.run_app(create_app(web_dir, user, password, upstream_port),
                host="0.0.0.0", port=listen_port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests/test_gateway.py -v`
Expected: PASS (async test needs pytest-asyncio already present in backend venv; if the async test errors with "async def not natively supported", add `asyncio_mode = "auto"` check — backend tests already run async, match their config).

- [ ] **Step 6: Commit**

```bash
git add agent/gateway.py agent/tests/test_gateway.py backend/pyproject.toml
git commit -m "feat(agent): authenticated gateway — dashboard static + websocket proxy"
```

---

### Task 9: styx_agent.py v0.4.0 — supervisor rework

Keep: config/TLS-pin/api/heartbeat/status/uninstall structure. Replace: the selkies-gstreamer process logic with three supervised processes (selkies-via-launcher, gateway, seat shell).

**Files:**
- Rewrite: `agent/styx_agent.py` (keep functions `load_config`, `_ssl_context`, `check_pin`, `api`, `_write_state`, `status`, `uninstall`, `main` as-is except noted)
- Rewrite: `agent/tests/test_styx_agent.py`

- [ ] **Step 1: Write the failing tests** (full file replacement — the old tests target the tarball engine)

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import styx_agent  # noqa: E402


def _cfg(tmp_path, **kw):
    cfg = {
        "server": "https://192.168.1.10", "agent_token": "tok",
        "workstation_id": "ws1", "port": 8443,
        "selkies_user": "styx", "selkies_password": "pw",
        "mode": "mirror", "display": ":1",
        "stream_settings": {"framerate": 60},
        "install_dir": str(tmp_path / "styx-agent"),
        "ca_pin": "", "server_cert": "",
    }
    cfg.update(kw)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return p, cfg


def test_load_config(tmp_path):
    p, _ = _cfg(tmp_path)
    assert styx_agent.load_config(p)["port"] == 8443


def test_agent_version_bumped():
    assert styx_agent.AGENT_VERSION == "0.4.0"


def test_gateway_cmd_secrets_via_env(tmp_path):
    _, cfg = _cfg(tmp_path)
    cmd, env = styx_agent.build_gateway_cmd(cfg)
    assert cmd[0].endswith("venv/bin/python")
    assert cmd[1].endswith("gateway.py")
    assert cmd[2].endswith("/web")
    assert cmd[3] == "8443"          # LAN port
    assert cmd[4] == "8444"          # loopback selkies
    assert env["STYX_GW_USER"] == "styx"
    assert env["STYX_GW_PASSWORD"] == "pw"
    assert not any("pw" in a for a in cmd)


def test_health_payload_reports_mode_and_engine(tmp_path):
    _, cfg = _cfg(tmp_path, mode="seat")
    h = styx_agent.health_payload(cfg, selkies_alive=True, gateway_alive=False)
    assert h["mode"] == "seat"
    assert h["engine"] == "pixelflux"
    assert h["agent_version"] == "0.4.0"
    assert h["selkies_alive"] is True and h["gateway_alive"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests/test_styx_agent.py -v`
Expected: FAIL (`build_gateway_cmd` missing, version 0.3.0)

- [ ] **Step 3: Rework `agent/styx_agent.py`**

Header/constants — change `AGENT_VERSION` to `"0.4.0"`. Delete `_gst_has_element`, `detect_encoder`, `XVFB_DISPLAY`, `_find_xauthority`, `display_plan`, `build_selkies_cmd`, `_start_xvfb`. Add after `load_config`:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402  (installed next to this file by enroll.sh)


def build_gateway_cmd(cfg: dict) -> tuple[list[str], dict]:
    install = Path(cfg["install_dir"])
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "STYX_GW_USER": cfg["selkies_user"],
        "STYX_GW_PASSWORD": cfg["selkies_password"],
    }
    cmd = [str(install / "venv/bin/python"), str(install / "gateway.py"),
           str(install / "web"), str(cfg["port"]),
           str(cfg["port"] + engine.INTERNAL_WS_OFFSET)]
    return cmd, env


def health_payload(cfg: dict, selkies_alive: bool, gateway_alive: bool) -> dict:
    return {
        "mode": cfg.get("mode", "mirror"),
        "engine": "pixelflux",
        "agent_version": AGENT_VERSION,
        "dri_node": engine.pick_dri_node(),
        "selkies_alive": selkies_alive,
        "gateway_alive": gateway_alive,
    }
```

Replace `run()` with:

```python
def run(cfg: dict) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    selkies_log = open(LOG_DIR / "selkies.log", "ab", buffering=0)
    gateway_log = open(LOG_DIR / "gateway.log", "ab", buffering=0)
    seat_log = open(LOG_DIR / "seat.log", "ab", buffering=0)

    seat_mode = cfg.get("mode") == "seat"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    procs: dict[str, subprocess.Popen | None] = {
        "selkies": None, "gateway": None, "shell": None}
    interval, backoff, stopping = 30, 2, False
    last_error: str | None = None

    def _stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    def start_selkies():
        nonlocal last_error
        try:
            cmd, env = engine.build_selkies_cmd(cfg)
        except Exception as e:
            last_error = f"engine setup failed: {e}"
            return None
        if seat_mode:
            try:
                monitor = engine.ensure_seat_sink()
                cmd = [a for a in cmd if not a.startswith("--audio-device-name=")]
                cmd.append(f"--audio-device-name={monitor}")
            except Exception:
                pass  # default-sink monitor still works; just leaks to speakers
        before = {p.name for p in Path(runtime_dir).glob("wayland-*")
                  if not p.name.endswith(".lock")}
        proc = subprocess.Popen(cmd, env=env, stdout=selkies_log,
                                stderr=selkies_log)
        if seat_mode:
            sock = engine.wait_for_wayland_socket(runtime_dir, before)
            if sock and shutil.which("labwc"):
                shell_env = {**os.environ, "WAYLAND_DISPLAY": sock,
                             "XDG_RUNTIME_DIR": runtime_dir}
                procs["shell"] = subprocess.Popen(
                    ["labwc"], env=shell_env, stdout=seat_log, stderr=seat_log)
            elif sock:
                last_error = ("labwc not installed — seat has no window "
                              "manager. Install: sudo apt install labwc")
        return proc

    while not stopping:
        if procs["selkies"] is None or procs["selkies"].poll() is not None:
            if procs["selkies"] is not None:
                print(f"selkies exited rc={procs['selkies'].returncode}; "
                      f"restart in {backoff}s", flush=True)
                time.sleep(min(backoff, 60))
                backoff *= 2
            procs["selkies"] = start_selkies()
        if procs["gateway"] is None or procs["gateway"].poll() is not None:
            cmd, env = build_gateway_cmd(cfg)
            procs["gateway"] = subprocess.Popen(cmd, env=env,
                                                stdout=gateway_log,
                                                stderr=gateway_log)
        selkies_ok = procs["selkies"] is not None and procs["selkies"].poll() is None
        gateway_ok = procs["gateway"] is not None and procs["gateway"].poll() is None
        if selkies_ok and gateway_ok:
            if last_error and not last_error.startswith("labwc"):
                last_error = None
        elif not selkies_ok and last_error is None:
            last_error = "selkies not running — see logs/selkies.log"

        try:
            hb = api(cfg, "/api/agent/heartbeat", {
                "status": "online" if selkies_ok and gateway_ok else "error",
                "last_error": last_error,
                "health": health_payload(cfg, selkies_ok, gateway_ok),
            })
            _write_state({"ts": time.time(), "ok": True, "state": hb["state"]})
            if hb["state"] == "revoked":
                print("Revoked by server. Stopping. To remove this agent run:\n"
                      f"  python3 {INSTALL_DIR / 'styx_agent.py'} uninstall",
                      flush=True)
                break
            if hb["stream_settings"] != cfg["stream_settings"]:
                cfg["stream_settings"] = hb["stream_settings"]
                CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
                for key in ("selkies", "shell"):
                    p = procs[key]
                    if p is not None and p.poll() is None:
                        p.terminate()
                        p.wait(timeout=10)
                    procs[key] = None
                continue
            interval = hb.get("heartbeat_interval_s", 30)
            backoff = 2
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            _write_state({"ts": time.time(), "ok": False, "error": str(e)})
            print(f"heartbeat failed: {e}", flush=True)
        time.sleep(interval)

    for p in procs.values():
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0
```

Replace `doctor()`'s selkies-specific checks:

```python
def doctor(cfg: dict) -> int:
    print("styx-agent doctor:")
    ok = True
    ok &= _check("config readable", True, str(CONFIG_PATH))
    install = Path(cfg["install_dir"])
    ok &= _check("venv present", (install / "venv/bin/python").exists())
    ok &= _check("web dist present", (install / "web/index.html").exists())
    ok &= _check("lib shim present", (install / "lib").is_dir(),
                 str(install / "lib"))
    ok &= _check(f"mode: {cfg.get('mode', 'mirror')}", True)
    if cfg.get("mode") == "mirror":
        xa = engine._find_xauthority(cfg)
        ok &= _check("XAUTHORITY found", xa is not None, xa or "none")
    dri = engine.pick_dri_node()
    _check("GPU render node", bool(dri), dri or "CPU encode")
    mon = engine.resolve_monitor_source()
    ok &= _check("audio monitor source", bool(mon), mon or "no pulse/pipewire")
    svc = subprocess.run(["systemctl", "--user", "is-active", "styx-agent"],
                         capture_output=True, text=True)
    ok &= _check("service active", svc.stdout.strip() == "active",
                 svc.stdout.strip())
    port_busy = socket.socket().connect_ex(("127.0.0.1", cfg["port"])) == 0
    ok &= _check(f"gateway listening :{cfg['port']}", port_busy,
                 "" if port_busy else "nothing listening — see logs/gateway.log")
    if cfg.get("ca_pin"):
        ok &= _check("TLS pin matches",
                     check_pin(cfg.get("server_cert", ""), cfg["ca_pin"]))
    try:
        api(cfg, "/api/agent/heartbeat", {"status": "online"})
        ok &= _check("server reachable + token valid", True)
    except Exception as e:
        ok &= _check("server reachable + token valid", False, str(e))
    print("All checks passed." if ok else f"Some checks failed. Logs: {LOG_DIR}")
    return 0 if ok else 1
```

Keep `uninstall()` but it already removes `INSTALL_DIR` (venv included) — no change needed.

- [ ] **Step 4: Run agent tests**

Run: `cd backend && .venv/bin/python -m pytest ../agent/tests -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add agent/styx_agent.py agent/tests/test_styx_agent.py
git commit -m "feat(agent): v0.4.0 supervisor — selkies+gateway+seat shell, health reporting"
```

---

### Task 10: enroll.sh rework

**Files:**
- Modify: `agent/enroll.sh`

- [ ] **Step 1: Apply these changes section by section**

**Args (lines 7-18):** add `--mode` (mirror|seat|auto, default auto); keep `--display`.

```bash
TOKEN="" SERVER="" CA_PIN="" FORCE_DISPLAY="" FORCE_MODE="auto"
...
    --display) FORCE_DISPLAY="$2"; shift 2 ;;   # implies --mode mirror
    --mode)    FORCE_MODE="$2"; shift 2 ;;       # mirror | seat | auto
```

**Step 1/8 (E01):** glibc floor 2.17 → 2.34, require python ≥3.10 + venv:

```bash
step 1/8 "Checking distro, glibc and python (E01)"
command -v python3 >/dev/null 2>&1 || fail E01 "python3 not found. Install it (apt install python3)."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || fail E01 "python3 >= 3.10 required (found $(python3 -V))."
python3 -c 'import venv' 2>/dev/null \
  || fail E01 "python3 venv module missing. Install: apt install python3-venv"
GLIBC=$(ldd --version 2>/dev/null | awk 'NR==1{for(i=NF;i>=1;i--) if($i ~ /^[0-9]+\.[0-9]+/){print $i; break}}')
GLIBC=${GLIBC:-0.0}
python3 - "$GLIBC" <<'PY' || fail E01 "glibc >= 2.34 required (found $GLIBC) — Ubuntu 22.04+/Debian 12+/RHEL 9+. The pixelflux wheels do not support older distros."
import sys
parts = sys.argv[1].split(".")
try:
    maj, mino = int(parts[0]), int(parts[1])
except (ValueError, IndexError):
    sys.exit(1)
sys.exit(0 if (maj, mino) >= (2, 34) else 1)
PY
note "python3 $(python3 -V | awk '{print $2}') + glibc $GLIBC OK"
```

**Step 2/8 (E02) — mode selection** (replace whole step):

```bash
step 2/8 "Choosing capture mode (E02)"
SESSION_TYPE="${XDG_SESSION_TYPE:-}"
[[ -z "$SESSION_TYPE" ]] && command -v loginctl >/dev/null && \
  SESSION_TYPE=$(loginctl show-session "$(loginctl --no-legend 2>/dev/null | awk '$3=="'"$USER"'"{print $1; exit}')" -p Type --value 2>/dev/null || true)
# shellcheck disable=SC2012
X_DISPLAYS=$(ls /tmp/.X11-unix/ 2>/dev/null | sed -n 's/^X\([0-9]\+\)$/:\1/p' | tr '\n' ' ')
if [[ -n "$FORCE_DISPLAY" ]]; then
  MODE="mirror"
elif [[ "$FORCE_MODE" != "auto" ]]; then
  MODE="$FORCE_MODE"
elif [[ "$SESSION_TYPE" == "x11" && -n "${DISPLAY:-}" ]]; then
  MODE="mirror"; FORCE_DISPLAY="$DISPLAY"
else
  MODE="seat"   # wayland session or headless: pixelflux runs its own seat
fi
if [[ "$MODE" == "mirror" ]]; then
  [[ -n "$FORCE_DISPLAY" ]] || { [[ -n "$X_DISPLAYS" ]] && FORCE_DISPLAY="${X_DISPLAYS%% *}"; }
  [[ -n "$FORCE_DISPLAY" ]] || fail E02 "Mirror mode needs an X display; none found. Use --mode seat instead."
  DISPLAY_SERVER="x11"
  note "Mirror mode — duplicating live X display $FORCE_DISPLAY (your session keeps control)."
else
  DISPLAY_SERVER="wayland"
  note "Second-seat mode — a private GPU desktop with this machine's apps and files."
  note "(Your physical screen is not mirrored; Wayland sessions cannot be captured.)"
fi
```

**Step 3/8 (E03) — dependencies:** replace `XVFB_PKG`/`WANT` logic; agent no longer needs Xvfb/openbox/xterm:

```bash
declare -A SEAT_PKG=( [apt]="labwc wl-clipboard" [dnf]="labwc wl-clipboard" [pacman]="labwc wl-clipboard" [zypper]="labwc wl-clipboard" )
declare -A VAAPI_PKG=( [apt]="mesa-va-drivers" [dnf]="mesa-va-drivers" [pacman]="libva-mesa-driver" [zypper]="libva" )
...
  WANT="${VAAPI_PKG[$MGR]}"
  [[ "$MODE" == "seat" ]] && WANT="$WANT ${SEAT_PKG[$MGR]}"
```

(keep the GPU_VENDOR detection block, but `vainfo` may be absent — change the VAAPI probe to `[[ -e /dev/dri/renderD128 ]] && GPU_VENDOR="vaapi"` with the nvidia-smi branch unchanged.)

**Step 7/8 — install** (replace the tarball block entirely):

```bash
step 7/8 "Installing agent (venv + wheels from portal cache)"
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$UNIT_DIR" "$INSTALL_DIR/logs"
for f in styx_agent.py engine.py gateway.py selkies_launcher.py; do
  fetch "$SERVER/api/enroll/${f/styx_agent.py/agent.py}" -o "$INSTALL_DIR/$f"
done
fetch "$SERVER/api/enroll/uninstall" -o "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/uninstall.sh"

note "downloading wheels + web dist + lib shim (cached on server)…"
for art in wheelhouse-x86_64.tar.gz selkies-web.tar.gz libshim-x86_64.tar.gz; do
  fetch "$SERVER/api/enroll/artifacts/$art" -o "$INSTALL_DIR/$art" \
    || fail E05 "Artifact $art unavailable. On the server run scripts/build_agent_artifacts.sh (see docs/WORKSTATIONS.md)."
done
tar -xzf "$INSTALL_DIR/wheelhouse-x86_64.tar.gz" -C "$INSTALL_DIR"     # -> wheelhouse/
tar -xzf "$INSTALL_DIR/selkies-web.tar.gz" -C "$INSTALL_DIR"           # -> web/
tar -xzf "$INSTALL_DIR/libshim-x86_64.tar.gz" -C "$INSTALL_DIR"        # -> lib/

note "creating venv (system python, prebuilt wheels only — no compiling)…"
# The wheelhouse already contains a `selkies` wheel built from the pinned
# tarball (Task 5 ran `pip wheel <url>`), so install everything by name with
# --no-index — nothing is ever compiled on the workstation.
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" -q install --no-index \
  --find-links "$INSTALL_DIR/wheelhouse" \
  selkies pixelflux==1.6.4 pcmflux setuptools aiohttp pulsectl \
  || fail E03 "Wheel install failed — likely an unsupported python version ($(python3 -V)). The wheelhouse covers python 3.10–3.13."
rm -rf "$INSTALL_DIR/wheelhouse" "$INSTALL_DIR"/*.tar.gz
```

**Step 8/8 — config:** in the embedded python that writes config.json, replace the `cfg = {...}` dict (keep the register call and response parsing) with:

```python
cfg = {"server": sys.argv[2], "agent_token": r["agent_token"],
       "workstation_id": r["workstation_id"], "port": r["port"],
       "selkies_user": r["selkies_user"], "selkies_password": r["selkies_password"],
       "mode": sys.argv[8], "display": sys.argv[7] or "",
       "stream_settings": r["stream_settings"],
       "install_dir": sys.argv[5], "ca_pin": sys.argv[3],
       "server_cert": (sys.argv[6] + "/server-cert.pem") if sys.argv[3] else ""}
```

and pass `"$MODE"` as the extra argv: the outer call becomes
`python3 - "$REGISTER_RESPONSE" "$SERVER" "$CA_PIN" "$DISPLAY_SERVER" "$INSTALL_DIR" "$CONFIG_DIR" "$FORCE_DISPLAY" "$MODE" <<'PY'`.
Also update the registration JSON's `"agent_version"` to `"0.4.0"`.

**Systemd unit:** change ExecStart to the venv interpreter — `engine`'s helpers lazily import venv-only packages (`Xlib` for geometry, `pulsectl` for audio), so the supervisor must run inside the venv:

```
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/styx_agent.py run
```

(`uninstall.sh`'s `python3` fallback path stays valid: `engine`'s top-level imports are stdlib-only; the venv-only imports are inside functions never reached during uninstall.)

- [ ] **Step 2: Syntax check**

Run: `bash -n agent/enroll.sh && shellcheck agent/enroll.sh || true`
Expected: `bash -n` silent; review shellcheck output for new-code issues only.

- [ ] **Step 3: Commit**

```bash
git add agent/enroll.sh
git commit -m "feat(agent): enroll v2 — venv from portal wheelhouse, mirror/seat mode detect"
```

---

### Task 11: docs

**Files:**
- Modify: `docs/WORKSTATIONS.md`

- [ ] **Step 1: Update**

Rewrite the engine-specific sections (read the current doc first; keep enrollment-token/UI sections):
- "How it works": mirror vs second-seat modes table (X11 host → live mirror w/ shared input; Wayland/headless → private GPU seat with host apps; physical Wayland screens cannot be mirrored — link spec).
- Requirements: Ubuntu 22.04+/Debian 12+/RHEL 9+ (glibc ≥2.34), python ≥3.10, PipeWire or PulseAudio; `labwc` auto-installed for seat mode.
- Server setup: run `scripts/build_agent_artifacts.sh ./data/artifacts` once (and after upgrades) — workstations download everything from the portal, LAN-only.
- Troubleshooting: `python3 ~/.local/share/styx-agent/styx_agent.py doctor`, log files (`logs/selkies.log`, `logs/gateway.log`, `logs/seat.log`), common errors (E01 glibc, E03 wheel install, artifact 503).
- Smoke-test checklist: replace v1 checklist with: enroll on X11 box → portal connect → see live desktop + audio + input; enroll with `--mode seat` → desktop appears, apps launch, audio plays, physical screen untouched.

- [ ] **Step 2: Commit**

```bash
git add docs/WORKSTATIONS.md
git commit -m "docs: workstation guide for native pixelflux engine (v2)"
```

---

### Task 12: Full verification + live smoke

- [ ] **Step 1: Full suites + lint**

```bash
cd backend && .venv/bin/python -m pytest -v && .venv/bin/python -m pytest ../agent/tests -v && .venv/bin/python -m ruff check app/ tests/
```
Expected: all PASS, lint clean.

- [ ] **Step 2: Build artifacts on this host**

Run: `./scripts/build_agent_artifacts.sh ./data/artifacts`
Expected: 3 tarballs in `./data/artifacts` (backend serves them via the artifacts volume — verify `docker compose config | grep -A3 artifacts` mounts match `ARTIFACT_CACHE_DIR`).

- [ ] **Step 3: Live enrollment smoke (this box doubles as workstation)**

Uninstall the v0.3.0 agent first: `python3 ~/.local/share/styx-agent/styx_agent.py uninstall`. Mint a token in the admin panel, run the LAN enroll command **with `--mode seat`** (the active GNOME session is Wayland; do NOT pass `--display :1` — the user's KasmVNC session must not be touched). Verify: portal shows Online; `/w/<sub>` renders the dashboard; desktop + audio stream; `doctor` all-OK.

- [ ] **Step 4: Final commit + memory**

Commit any smoke fixes individually with descriptive messages. Update `~/.claude/.../memory/workstation-streaming.md` status line.
