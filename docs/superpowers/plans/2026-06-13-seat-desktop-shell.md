# Seat Desktop Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the workstation agent's seat-mode desktop (a bare labwc compositor captured by pixelflux) into a GNOME-like desktop: top panel with system tray, full-screen app grid, bottom dock, and dark mode.

**Architecture:** All changes live in `agent/`. `engine.py`'s `write_seat_config()` is rewritten to generate a real shell: labwc (`rc.xml`/`environment`/`menu.xml`/`autostart`) plus a waybar config. The autostart launches waybar, `nwg-dock`, dark-mode pushes, and wallpaper — each `command -v`-guarded so missing tools degrade gracefully. waybar is launched with **explicit `-c`/`-s` config paths** (not `XDG_CONFIG_HOME`) so the user's real `~/.config` and host-app profiles are never touched. `enroll.sh` gains the new seat packages.

**Tech Stack:** Python 3.12 (stdlib only), labwc, waybar, nwg-drawer/nwg-dock, fuzzel, swaybg, pytest.

---

## File Structure

| File | Responsibility |
|---|---|
| `agent/engine.py` | New helpers (`pick_launcher`, `pick_file_manager`, `scan_desktop_entries`) + config builders (`build_root_menu`, `build_waybar_config`, `build_labwc_rc`, `build_labwc_environment`, `build_autostart`); rewritten `write_seat_config()` orchestrator. |
| `agent/tests/test_engine.py` | Unit tests for each helper + the orchestrator (mock `shutil.which` / filesystem). |
| `agent/enroll.sh` | Extend `SEAT_PKG` per-distro maps with the new shell deps. |

`write_seat_config(config_dir)` keeps its single-arg signature (`config_dir` = `$INSTALL_DIR/labwc`, passed by `styx_agent.py:154`). It derives the waybar dir as `config_dir.parent / "waybar"`. **`styx_agent.py` is not modified.**

---

### Task 1: `pick_launcher()` — launcher fallback chain

**Files:**
- Modify: `agent/engine.py` (add near `pick_terminal`, ~line 188)
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pick_launcher_prefers_grid_then_fuzzel(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n == "nwg-drawer" else None)
    assert engine.pick_launcher() == "nwg-drawer"
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/fuzzel" if n == "fuzzel" else None)
    assert engine.pick_launcher() == "fuzzel"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert engine.pick_launcher() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py::test_pick_launcher_prefers_grid_then_fuzzel -v`
Expected: FAIL — `AttributeError: module 'engine' has no attribute 'pick_launcher'`

- [ ] **Step 3: Write minimal implementation**

Add to `agent/engine.py` (after `pick_terminal`):

```python
LAUNCHERS = ("nwg-drawer", "fuzzel")


def pick_launcher() -> str:
    """Full-screen app grid (nwg-drawer) preferred, then a compact search
    launcher (fuzzel). Empty string -> caller falls back to labwc root menu."""
    import shutil
    for name in LAUNCHERS:
        if shutil.which(name):
            return name
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py::test_pick_launcher_prefers_grid_then_fuzzel -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): pick_launcher fallback chain for seat shell"
```

---

### Task 2: `pick_file_manager()` — host file-manager detection

**Files:**
- Modify: `agent/engine.py`
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pick_file_manager_detection_order(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n in ("thunar", "nemo") else None)
    # nemo ranks above thunar in the order
    assert engine.pick_file_manager() == "nemo"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert engine.pick_file_manager() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py::test_pick_file_manager_detection_order -v`
Expected: FAIL — no attribute `pick_file_manager`

- [ ] **Step 3: Write minimal implementation**

```python
FILE_MANAGERS = ("nautilus", "nemo", "thunar", "pcmanfm-qt", "pcmanfm", "dolphin")


def pick_file_manager() -> str:
    """First GUI file manager present on the host. Empty if none."""
    import shutil
    for name in FILE_MANAGERS:
        if shutil.which(name):
            return name
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py::test_pick_file_manager_detection_order -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): pick_file_manager host detection"
```

---

### Task 3: `scan_desktop_entries()` — parse installed `.desktop` apps

**Files:**
- Modify: `agent/engine.py`
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_scan_desktop_entries_parses_and_filters(tmp_path):
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "firefox.desktop").write_text(
        "[Desktop Entry]\nName=Firefox\nExec=firefox %u\nType=Application\n")
    (apps / "hidden.desktop").write_text(
        "[Desktop Entry]\nName=Secret\nExec=secret\nNoDisplay=true\n")
    (apps / "noexec.desktop").write_text(
        "[Desktop Entry]\nName=Broken\nType=Application\n")
    entries = engine.scan_desktop_entries([str(apps)])
    assert entries == [("Firefox", "firefox")]   # field code stripped, others filtered


def test_scan_desktop_entries_skips_missing_dirs():
    assert engine.scan_desktop_entries(["/no/such/dir"]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py::test_scan_desktop_entries_parses_and_filters agent/tests/test_engine.py::test_scan_desktop_entries_skips_missing_dirs -v`
Expected: FAIL — no attribute `scan_desktop_entries`

- [ ] **Step 3: Write minimal implementation**

Add module constant near the top-level constants and the function:

```python
APPLICATIONS_DIRS = ["/usr/share/applications",
                     "/usr/local/share/applications",
                     str(HOME / ".local/share/applications")]


def scan_desktop_entries(dirs=None) -> list:
    """(Name, Exec) pairs from .desktop files. Skips NoDisplay/Hidden and
    entries missing Name or Exec. Strips Exec field codes (%u %F etc.).
    De-duplicated by name, sorted. First [Desktop Entry] values win."""
    dirs = dirs if dirs is not None else APPLICATIONS_DIRS
    seen = {}
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*.desktop")):
            name = exec_ = ""
            skip = False
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for line in text.splitlines():
                if line.startswith("[") and name:
                    break                       # past first [Desktop Entry]
                if line.startswith("Name=") and not name:
                    name = line[5:].strip()
                elif line.startswith("Exec=") and not exec_:
                    exec_ = line[5:].strip()
                elif line.startswith(("NoDisplay=true", "Hidden=true")):
                    skip = True
            if skip or not name or not exec_:
                continue
            exec_ = " ".join(t for t in exec_.split()
                             if not (len(t) == 2 and t.startswith("%")))
            seen.setdefault(name, exec_)
    return sorted(seen.items())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k scan_desktop_entries -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): scan_desktop_entries for seat app menu"
```

---

### Task 4: `build_root_menu()` — labwc menu from entries (replaces static `_SEAT_MENU`)

**Files:**
- Modify: `agent/engine.py` (remove `_SEAT_MENU` constant)
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_root_menu_includes_files_apps_and_escapes(tmp_path):
    xml = engine.build_root_menu(
        [("Rofi & Co", "rofi"), ("Term", "xterm")],
        term="foot", file_mgr="thunar", home="/home/u")
    assert "<action name=\"Execute\" command=\"thunar /home/u\"/>" in xml
    assert "Files" in xml
    assert "Rofi &amp; Co" in xml          # XML-escaped label
    assert "<action name=\"Exit\"/>" in xml
    assert "Applications" in xml


def test_build_root_menu_without_file_manager():
    xml = engine.build_root_menu([], term="foot", file_mgr="", home="/home/u")
    assert "Files" not in xml
    assert "foot" in xml                    # Terminal entry still present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k build_root_menu -v`
Expected: FAIL — no attribute `build_root_menu`

- [ ] **Step 3: Write minimal implementation**

Delete the `_SEAT_MENU = """..."""` constant (lines ~171-179). Add:

```python
def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _menu_item(label: str, command: str) -> str:
    return (f'  <item label="{_xml_escape(label)}">'
            f'<action name="Execute" command="{command}"/></item>')


def build_root_menu(entries, term: str, file_mgr: str, home: str) -> str:
    """labwc/openbox root menu: Files + Terminal at top, an Applications
    submenu built from `entries`, then Reconfigure/Exit."""
    apps = "\n".join(_menu_item(n, e) for n, e in entries) or \
        '  <item label="(no apps found)"><action name="Reconfigure"/></item>'
    top = []
    if file_mgr:
        top.append(_menu_item("Files", f"{file_mgr} {home}"))
    if term:
        top.append(_menu_item("Terminal", term))
    top_xml = "\n".join(top)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<openbox_menu>
<menu id="apps-menu" label="Applications">
{apps}
</menu>
<menu id="root-menu" label="Styx">
{top_xml}
  <menu id="apps-menu"/>
  <separator/>
  <item label="Reconfigure"><action name="Reconfigure"/></item>
  <item label="Exit session"><action name="Exit"/></item>
</menu>
</openbox_menu>
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k build_root_menu -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): dynamic labwc root menu from .desktop entries"
```

---

### Task 5: `build_waybar_config()` — top panel with SNI tray

**Files:**
- Modify: `agent/engine.py` (add `import json` at top if absent)
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_waybar_config_has_tray_and_menu(monkeypatch):
    import json as _json
    cfg_str, style = engine.build_waybar_config("nwg-drawer")
    cfg = _json.loads(cfg_str)
    assert "tray" in cfg["modules-right"]                 # Toolbox docks here
    assert cfg["custom/menu"]["on-click"] == "nwg-drawer"
    assert cfg["position"] == "top"
    assert "wlr/taskbar" in cfg["modules-left"]
    assert "#waybar" in style and "background" in style    # dark css


def test_build_waybar_config_menu_falls_back_when_no_launcher():
    cfg_str, _ = engine.build_waybar_config("")
    import json as _json
    assert _json.loads(cfg_str)["custom/menu"]["on-click"] == "true"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k build_waybar_config -v`
Expected: FAIL — no attribute `build_waybar_config`

- [ ] **Step 3: Write minimal implementation**

Ensure `import json` is present at the top of `agent/engine.py` (add it if not). Add:

```python
def build_waybar_config(launcher: str) -> tuple:
    """(config_json, style_css) for the top panel. `tray` is waybar's built-in
    StatusNotifier host — JetBrains Toolbox and other SNI apps dock there."""
    menu_cmd = launcher or "true"
    config = {
        "layer": "top", "position": "top", "height": 32,
        "modules-left": ["custom/menu", "wlr/taskbar"],
        "modules-center": ["clock"],
        "modules-right": ["tray", "pulseaudio", "network", "custom/power"],
        "custom/menu": {"format": "  Apps", "on-click": menu_cmd, "tooltip": False},
        "wlr/taskbar": {"on-click": "activate", "all-outputs": True},
        "clock": {"format": "{:%a %d %b  %H:%M}"},
        "tray": {"spacing": 8, "icon-size": 18},
        "pulseaudio": {"format": "{icon} {volume}%",
                       "format-muted": "muted",
                       "format-icons": ["", "", ""],
                       "on-click": "pavucontrol"},
        "network": {"format-wifi": "{essid}", "format-ethernet": "wired",
                    "format-disconnected": "offline"},
        "custom/power": {"format": "Exit", "on-click": "labwc --exit",
                         "tooltip": False},
    }
    style = (
        '* { font-family: "Noto Sans", sans-serif; font-size: 13px; }\n'
        "window#waybar { background: #1d2433; color: #e6e9ef; }\n"
        "#custom-menu { padding: 0 14px; background: #2b3650; color: #ffffff; }\n"
        "#clock, #pulseaudio, #network, #tray, #custom-power { padding: 0 10px; }\n"
        "#taskbar button.active { background: #2b3650; }\n"
    )
    return json.dumps(config, indent=2), style
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k build_waybar_config -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): waybar top panel config with SNI tray"
```

---

### Task 6: `build_labwc_rc()` + `build_labwc_environment()` — keybinds & dark env

**Files:**
- Modify: `agent/engine.py`
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_labwc_rc_binds_super_to_launcher():
    rc = engine.build_labwc_rc("nwg-drawer", "foot")
    assert 'key="W-d"' in rc and "nwg-drawer" in rc
    assert 'key="W-Return"' in rc and "foot" in rc


def test_build_labwc_rc_no_launcher_is_noop_command():
    rc = engine.build_labwc_rc("", "foot")
    assert 'command="true"' in rc            # Super bound to a harmless no-op


def test_build_labwc_environment_forces_dark():
    env = engine.build_labwc_environment()
    assert "GTK_THEME=Adwaita-dark" in env
    assert "XCURSOR_THEME=Adwaita" in env
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k "labwc_rc or labwc_environment" -v`
Expected: FAIL — no attribute `build_labwc_rc`

- [ ] **Step 3: Write minimal implementation**

```python
def build_labwc_rc(launcher: str, term: str) -> str:
    """labwc keybinds: Super+D / Super opens the launcher, Super+Enter a
    terminal. `launcher` empty -> bound to `true` (no-op)."""
    launch = launcher or "true"
    term = term or "true"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<labwc_config>
  <theme><cornerRadius>4</cornerRadius></theme>
  <keyboard>
    <keybind key="W-d"><action name="Execute" command="{launch}"/></keybind>
    <keybind key="Super_L"><action name="Execute" command="{launch}"/></keybind>
    <keybind key="W-Return"><action name="Execute" command="{term}"/></keybind>
    <keybind key="A-Tab"><action name="NextWindow"/></keybind>
  </keyboard>
</labwc_config>
"""


def build_labwc_environment() -> str:
    """labwc `environment` file — exported for the whole seat session so GTK/Qt
    apps render dark. Affects theming only, not config paths."""
    return ("GTK_THEME=Adwaita-dark\n"
            "XCURSOR_THEME=Adwaita\n"
            "XCURSOR_SIZE=24\n"
            "QT_QPA_PLATFORM=wayland;xcb\n"
            "QT_STYLE_OVERRIDE=Adwaita-Dark\n"
            "MOZ_ENABLE_WAYLAND=1\n"
            "XDG_CURRENT_DESKTOP=labwc:wlroots\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k "labwc_rc or labwc_environment" -v`
Expected: PASS (all three)

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): labwc rc keybinds + dark environment for seat"
```

---

### Task 7: `build_autostart()` — guarded launch lines (wallpaper, dark push, panel, dock)

**Files:**
- Modify: `agent/engine.py`
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_autostart_emits_guarded_lines():
    sh = engine.build_autostart(
        launcher="nwg-drawer",
        waybar_config="/i/waybar/config", waybar_style="/i/waybar/style.css")
    assert sh.startswith("#!/bin/sh")
    assert 'command -v swaybg >/dev/null && swaybg -c "#1d2433" &' in sh
    assert "color-scheme 'prefer-dark'" in sh
    assert 'waybar -c "/i/waybar/config" -s "/i/waybar/style.css" &' in sh
    assert 'nwg-dock -d -i 36 -l "nwg-drawer" &' in sh
    assert "xdg-desktop-portal" in sh


def test_build_autostart_dock_without_launcher_has_no_l_flag():
    sh = engine.build_autostart(launcher="",
                                waybar_config="/i/waybar/config",
                                waybar_style="/i/waybar/style.css")
    assert "nwg-dock -d -i 36 &" in sh
    assert " -l " not in sh
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k build_autostart -v`
Expected: FAIL — no attribute `build_autostart`

- [ ] **Step 3: Write minimal implementation**

```python
def build_autostart(launcher: str, waybar_config: str, waybar_style: str) -> str:
    """labwc autostart: wallpaper, dark-mode push, portal, panel, dock — each
    guarded by `command -v` so a missing tool is silently skipped. waybar gets
    explicit -c/-s paths (NOT XDG_CONFIG_HOME) so host apps keep their own
    ~/.config."""
    dock = (f'nwg-dock -d -i 36 -l "{launcher}" &' if launcher
            else "nwg-dock -d -i 36 &")
    return "\n".join([
        "#!/bin/sh",
        "# generated by styx agent — regenerated each seat start; do not edit",
        'command -v swaybg >/dev/null && swaybg -c "#1d2433" &',
        "if command -v gsettings >/dev/null; then",
        "  gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark' 2>/dev/null",
        "  gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita-dark' 2>/dev/null",
        "  gsettings set org.gnome.desktop.interface icon-theme 'Adwaita' 2>/dev/null",
        "  gsettings set org.gnome.desktop.interface cursor-theme 'Adwaita' 2>/dev/null",
        "fi",
        "command -v /usr/libexec/xdg-desktop-portal >/dev/null && "
        "/usr/libexec/xdg-desktop-portal &",
        f'command -v waybar >/dev/null && waybar -c "{waybar_config}" '
        f'-s "{waybar_style}" &',
        f"command -v nwg-dock >/dev/null && {dock}",
        "",
    ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k build_autostart -v`
Expected: PASS (both)

- [ ] **Step 5: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): seat autostart — wallpaper, dark push, panel, dock"
```

---

### Task 8: Rewrite `write_seat_config()` — orchestrate all generators

**Files:**
- Modify: `agent/engine.py` (replace body of `write_seat_config`, ~lines 190-208)
- Test: `agent/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

```python
def test_write_seat_config_emits_all_files(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n in
                        ("nwg-drawer", "foot", "thunar", "waybar", "nwg-dock",
                         "swaybg") else None)
    monkeypatch.setattr(engine, "scan_desktop_entries",
                        lambda *a: [("Firefox", "firefox")])
    labwc = tmp_path / "install" / "labwc"
    engine.write_seat_config(labwc)
    # labwc dir
    assert (labwc / "autostart").read_text().startswith("#!/bin/sh")
    assert (labwc / "autostart").stat().st_mode & 0o111      # executable
    assert "Firefox" in (labwc / "menu.xml").read_text()
    assert "nwg-drawer" in (labwc / "rc.xml").read_text()
    assert "Adwaita-dark" in (labwc / "environment").read_text()
    # waybar dir is a sibling of labwc, NOT under ~/.config
    wb = tmp_path / "install" / "waybar"
    assert "tray" in (wb / "config").read_text()
    assert "#waybar" in (wb / "style.css").read_text()


def test_write_seat_config_degrades_without_optional_tools(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda n: None)     # nothing installed
    monkeypatch.setattr(engine, "scan_desktop_entries", lambda *a: [])
    labwc = tmp_path / "install" / "labwc"
    engine.write_seat_config(labwc)                          # must not raise
    # launcher empty -> menu on-click is the no-op
    import json as _json
    cfg = _json.loads((tmp_path / "install" / "waybar" / "config").read_text())
    assert cfg["custom/menu"]["on-click"] == "true"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k write_seat_config -v`
Expected: FAIL — old `write_seat_config` writes no `rc.xml`/`environment`/waybar files (KeyError/FileNotFound on assertions).

- [ ] **Step 3: Write minimal implementation**

Replace the entire `write_seat_config` function body with:

```python
def write_seat_config(config_dir: Path) -> None:
    """Generate the full seat desktop shell. `config_dir` is the labwc config
    dir ($INSTALL_DIR/labwc); the waybar config is written to its sibling
    $INSTALL_DIR/waybar. Regenerated each shell start so newly installed tools
    are picked up on restart. Every launch line is command-v-guarded, so a host
    missing waybar/nwg-*/swaybg still gets a working (if barer) session."""
    config_dir.mkdir(parents=True, exist_ok=True)
    waybar_dir = config_dir.parent / "waybar"
    waybar_dir.mkdir(parents=True, exist_ok=True)

    term = pick_terminal()
    launcher = pick_launcher()
    file_mgr = pick_file_manager()
    entries = scan_desktop_entries()

    cfg_json, style = build_waybar_config(launcher)
    (waybar_dir / "config").write_text(cfg_json)
    (waybar_dir / "style.css").write_text(style)

    auto = config_dir / "autostart"
    auto.write_text(build_autostart(launcher,
                                    str(waybar_dir / "config"),
                                    str(waybar_dir / "style.css")))
    auto.chmod(0o755)
    (config_dir / "menu.xml").write_text(
        build_root_menu(entries, term, file_mgr, str(HOME)))
    (config_dir / "rc.xml").write_text(build_labwc_rc(launcher, term))
    (config_dir / "environment").write_text(build_labwc_environment())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/test_engine.py -k write_seat_config -v`
Expected: PASS (both)

- [ ] **Step 5: Run the full agent suite + lint**

Run: `cd /home/user/code/remote-access && backend/.venv/bin/python -m pytest agent/tests/ -v && backend/.venv/bin/python -m ruff check agent/`
Expected: all PASS, ruff clean. (If ruff flags the `import json`/line length, fix inline.)

- [ ] **Step 6: Commit**

```bash
git add agent/engine.py agent/tests/test_engine.py
git commit -m "feat(agent): rewrite write_seat_config to build full GNOME-like seat shell"
```

---

### Task 9: Extend `enroll.sh` `SEAT_PKG` with shell dependencies

**Files:**
- Modify: `agent/enroll.sh` (the `declare -A SEAT_PKG=(...)` line, ~line 154)

No unit test (shell install path); verify with `bash -n` + `shellcheck`.

- [ ] **Step 1: Replace the `SEAT_PKG` map**

Find (around line 154):

```bash
declare -A SEAT_PKG=( [apt]="labwc xwayland waybar swaybg foot wl-clipboard" [dnf]="labwc xorg-x11-server-Xwayland waybar swaybg foot wl-clipboard" [pacman]="labwc xorg-xwayland waybar swaybg foot wl-clipboard" [zypper]="labwc xwayland waybar swaybg foot wl-clipboard" )
```

Replace with (adds launcher, dock, fallback launcher, file manager, dark-theme + portal packages; per-distro names differ):

```bash
declare -A SEAT_PKG=( \
  [apt]="labwc xwayland waybar swaybg foot wl-clipboard nwg-drawer nwg-dock fuzzel thunar xdg-desktop-portal-gtk gnome-themes-extra adwaita-icon-theme" \
  [dnf]="labwc xorg-x11-server-Xwayland waybar swaybg foot wl-clipboard nwg-drawer nwg-dock fuzzel thunar xdg-desktop-portal-gtk gnome-themes-extra adwaita-icon-theme" \
  [pacman]="labwc xorg-xwayland waybar swaybg foot wl-clipboard nwg-drawer nwg-dock fuzzel thunar xdg-desktop-portal-gtk gnome-themes-extra adwaita-icon-theme" \
  [zypper]="labwc xwayland waybar swaybg foot wl-clipboard nwg-drawer nwg-dock fuzzel thunar xdg-desktop-portal-gtk gnome-themes-extra adwaita-icon-theme" )
```

- [ ] **Step 2: Update the failure-hint note**

Find (around line 168):

```bash
    note "WARNING (E03): dependency install failed. For seat mode install"
    note "  labwc + wl-clipboard manually, then restart styx-agent."
```

Replace the second line with a fuller hint:

```bash
    note "WARNING (E03): dependency install failed. For seat mode install"
    note "  labwc waybar swaybg foot wl-clipboard (+ optional nwg-drawer nwg-dock"
    note "  fuzzel thunar xdg-desktop-portal-gtk) manually, then restart styx-agent."
```

- [ ] **Step 3: Syntax-check the script**

Run: `cd /home/user/code/remote-access && bash -n agent/enroll.sh && { command -v shellcheck >/dev/null && shellcheck -S warning agent/enroll.sh || echo "shellcheck not installed — bash -n only"; }`
Expected: no syntax errors. (Pre-existing shellcheck warnings unrelated to this change may remain; do not fix unrelated ones.)

- [ ] **Step 4: Commit**

```bash
git add agent/enroll.sh
git commit -m "feat(enroll): install seat desktop shell deps (nwg-drawer/dock, fuzzel, portal, dark theme)"
```

---

## Self-Review

**Spec coverage:**
- Top bar + dock + app grid → Tasks 5 (waybar), 7 (dock launch), 1+6 (launcher binding). ✓
- SNI tray (Toolbox) → Task 5 `tray` module. ✓
- Dark mode (gsettings + portal + GTK_THEME) → Tasks 6 (`environment`), 7 (autostart push). ✓
- App menu from `.desktop` → Tasks 3 + 4. ✓
- Files/folders via file manager (no bg icons) → Tasks 2 + 4 (root-menu Files) + 7 (dock pin via `-l`). ✓
- Isolated config (no `~/.config` clobber) → Task 8 sibling `waybar` dir + explicit `-c/-s`; refinement over the spec's `XDG_CONFIG_HOME` (which would have redirected host apps' configs). ✓
- New deps in `SEAT_PKG` per-distro → Task 9. ✓
- Graceful degradation → Tasks 1 (fallback chain), 7 (`command -v` guards), 8 (degrade test). ✓
- Tests → every task is TDD. ✓
- Out of scope (bg icons, mirror mode, pixelflux/backend/Docker) → untouched. ✓

**Placeholder scan:** none — every code/test step is complete.

**Type consistency:** `build_waybar_config` returns `(str, str)` consumed in Task 8; `scan_desktop_entries` returns `list[(name, exec)]` consumed by `build_root_menu`; `pick_launcher`/`pick_file_manager`/`pick_terminal` all return `str`; `build_autostart(launcher, waybar_config, waybar_style)` signature matches the Task 8 call. Consistent.

**Note:** `styx_agent.py` is intentionally unchanged — the `XDG_CONFIG_HOME` approach from the spec was dropped in favor of explicit waybar `-c/-s` paths to avoid breaking host apps' own config lookup.
