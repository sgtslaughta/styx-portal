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
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert cmd[0].endswith("venv/bin/python")
    assert cmd[1].endswith("selkies_launcher.py")
    assert "--port=18444" in cmd
    assert "--control-port=18445" in cmd
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
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert env["PIXELFLUX_WAYLAND"] == "true"
    assert env["DRINODE"] == "/dev/dri/renderD128"
    assert "DISPLAY" not in env
    assert "--is-manual-resolution-mode=true" not in cmd
    assert "--wayland-socket-index=1" in cmd      # default until detected


def test_seat_cmd_uses_persisted_socket_index(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="", seat_socket_index=3)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, _ = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert "--wayland-socket-index=3" in cmd


def test_seat_cmd_without_gpu_falls_back_to_cpu(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "styx-seat.monitor")
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert "DRINODE" not in env
    assert not any(a.startswith("--dri-node") for a in cmd)


def test_audio_disabled_when_no_pulse(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, xa: (1920, 1080))
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg, 18444, 18445)
    assert env["SELKIES_AUDIO_ENABLED"] == "false"


def test_wait_for_wayland_socket(tmp_path):
    import time
    (tmp_path / "wayland-1").touch()
    name = engine.wait_for_wayland_socket(str(tmp_path), set(),
                                          since_ts=time.time() + 60, timeout=1)
    assert name == "wayland-1"          # new name counts even with future ts
    assert engine.wait_for_wayland_socket(str(tmp_path), {"wayland-1"},
                                          since_ts=time.time() + 60,
                                          timeout=0.2) is None


def test_wait_for_wayland_socket_excludes_seat_socket(tmp_path):
    # Both sockets are fresh (within the mtime slack). Without exclude, the
    # lexically-first (the seat's own wayland-1) is wrongly returned; with
    # exclude we must get labwc's wayland-2.
    import time
    (tmp_path / "wayland-1").touch()
    (tmp_path / "wayland-2").touch()
    since = time.time() - 60
    assert engine.wait_for_wayland_socket(
        str(tmp_path), {"wayland-1", "wayland-2"}, since_ts=since,
        timeout=1) == "wayland-1"  # default: first match
    assert engine.wait_for_wayland_socket(
        str(tmp_path), {"wayland-1", "wayland-2"}, since_ts=since,
        timeout=1, exclude={"wayland-1"}) == "wayland-2"  # seat excluded


def test_wait_for_wayland_socket_stale_file_rebound(tmp_path):
    # Socket file survived a previous run (name in `before`) but the
    # compositor recreated it after since_ts -> must be detected.
    import time
    (tmp_path / "wayland-1").touch()
    name = engine.wait_for_wayland_socket(str(tmp_path), {"wayland-1"},
                                          since_ts=time.time() - 60, timeout=1)
    assert name == "wayland-1"


def test_guard_default_socket_holds_slot0_and_clears_stale(tmp_path):
    """Guard flocks wayland-0.lock (libwayland's own convention) so neither
    seat compositor can bind the slot that WAYLAND_DISPLAY-less host apps
    fall back to, and removes a stale wayland-0 socket file."""
    import fcntl
    (tmp_path / "wayland-0").touch()        # stale socket from a prior run
    guard = engine.guard_default_socket(str(tmp_path))
    assert guard is not None
    assert not (tmp_path / "wayland-0").exists()
    # Slot now contended: a second taker (compositor) must be refused
    f = open(tmp_path / "wayland-0.lock", "a+")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raised = False
        except OSError:
            raised = True
        assert raised
    finally:
        f.close()
    guard.close()


def test_guard_default_socket_yields_to_live_owner(tmp_path):
    """If a real Wayland session already holds the slot-0 lock, back off."""
    import fcntl
    owner = open(tmp_path / "wayland-0.lock", "a+")
    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert engine.guard_default_socket(str(tmp_path)) is None
    finally:
        owner.close()


def test_pick_dri_node(tmp_path, monkeypatch):
    dri = tmp_path / "dri"
    dri.mkdir()
    (dri / "renderD128").touch()
    monkeypatch.setattr(engine, "DRI_DIR", str(dri))
    assert engine.pick_dri_node().endswith("renderD128")
    monkeypatch.setattr(engine, "DRI_DIR", str(tmp_path / "nope"))
    assert engine.pick_dri_node() == ""


def test_pick_free_port():
    p = engine.pick_free_port()
    assert 1024 < p < 65536


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


def test_pick_file_manager_detection_order(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n in ("thunar", "nemo") else None)
    # nemo ranks above thunar in the order
    assert engine.pick_file_manager() == "nemo"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert engine.pick_file_manager() == ""


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


def test_build_root_menu_includes_files_apps_and_escapes(tmp_path):
    xml = engine.build_root_menu(
        [("Rofi & Co", "rofi"), ("Term", "xterm")],
        term="foot", file_mgr="thunar", home="/home/u")
    assert "<action name=\"Execute\" command=\"thunar /home/u\"/>" in xml
    assert "Files" in xml
    assert "Rofi &amp; Co" in xml          # XML-escaped label
    assert "<action name=\"Exit\"/>" in xml
    assert "Applications" in xml


def test_build_root_menu_escapes_command_attribute():
    xml = engine.build_root_menu([("App", "run & thing")],
                                 term="", file_mgr="", home="/h")
    assert "run &amp; thing" in xml


def test_build_root_menu_without_file_manager():
    xml = engine.build_root_menu([], term="foot", file_mgr="", home="/home/u")
    assert "Files" not in xml
    assert "foot" in xml                    # Terminal entry still present


def test_build_waybar_config_has_tray_and_menu(monkeypatch):
    import json as _json
    cfg_str, style = engine.build_waybar_config("nwg-drawer")
    cfg = _json.loads(cfg_str)
    assert "tray" in cfg["modules-right"]                 # Toolbox docks here
    assert cfg["custom/menu"]["on-click"] == "nwg-drawer"
    assert cfg["position"] == "top"
    assert cfg["modules-left"] == ["custom/menu"]
    assert "wlr/taskbar" not in cfg["modules-left"]        # tasks live on the dock
    assert "custom/power" not in cfg["modules-right"]      # no Exit (kills UI unrecoverably)
    assert "labwc --exit" not in cfg_str
    assert "#waybar" in style and "background" in style    # dark css


def test_build_waybar_config_menu_falls_back_when_no_launcher():
    cfg_str, _ = engine.build_waybar_config("")
    import json as _json
    assert _json.loads(cfg_str)["custom/menu"]["on-click"] == "true"


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


def test_build_autostart_emits_guarded_lines():
    sh = engine.build_autostart(
        waybar_config="/i/waybar/config", waybar_style="/i/waybar/style.css",
        dock_config="/i/waybar/dock-config", dock_style="/i/waybar/dock-style.css")
    assert sh.startswith("#!/bin/sh")
    assert 'command -v swaybg >/dev/null && swaybg -c "#1d2433" &' in sh
    assert "color-scheme 'prefer-dark'" in sh
    assert 'waybar -c "/i/waybar/config" -s "/i/waybar/style.css" &' in sh
    assert 'waybar -c "/i/waybar/dock-config" -s "/i/waybar/dock-style.css" &' in sh
    assert "nwg-dock" not in sh              # sway-only; never launched on labwc
    assert "xdg-desktop-portal-gtk" in sh   # Settings backend → dark in browsers
    assert "$d/xdg-desktop-portal" in sh    # frontend launched from libexec


def test_build_waybar_dock_has_taskbar_and_pins():
    import json as _json
    cfg_str, style = engine.build_waybar_dock("nwg-drawer", "foot", "thunar",
                                              "firefox")
    cfg = _json.loads(cfg_str)
    assert cfg["position"] == "bottom"
    assert "wlr/taskbar" in cfg["modules-center"]
    assert "custom/apps" in cfg["modules-center"]      # pinned launcher button
    assert cfg["custom/apps"]["on-click"] == "nwg-drawer"
    assert cfg["custom/web"]["on-click"].startswith("firefox ")
    assert "#taskbar" in style


def test_build_waybar_dock_skips_absent_pins():
    import json as _json
    cfg_str, _ = engine.build_waybar_dock("", "", "", "")
    cfg = _json.loads(cfg_str)
    assert cfg["modules-center"] == ["wlr/taskbar"]    # no pins when nothing found


def test_browser_launch_cmd_chrome_isolates_instance_and_forces_wayland():
    # A chrome already running in the user's :0/VNC session owns the shared
    # profile's singleton, so a plain launch just opens a window THERE. A
    # dedicated --user-data-dir gives the seat its own instance; --ozone forces
    # it onto the Wayland seat instead of $DISPLAY (=:0, the VNC server).
    for browser in ("google-chrome", "chromium", "chromium-browser"):
        cmd = engine.browser_launch_cmd(browser)
        assert cmd.startswith(f"{browser} ")
        assert "--ozone-platform=wayland" in cmd
        assert "--user-data-dir=" in cmd
        assert "styx-seat" in cmd          # a separate, seat-only profile dir


def test_browser_launch_cmd_firefox_isolates_instance():
    # Same singleton trap for Firefox: --no-remote + a dedicated profile force a
    # new instance rather than routing to a :0-session Firefox. Wayland comes
    # from MOZ_ENABLE_WAYLAND in the labwc environment file.
    cmd = engine.browser_launch_cmd("firefox")
    assert cmd.startswith("firefox ")
    assert "--no-remote" in cmd
    assert "--profile" in cmd
    assert engine.browser_launch_cmd("") == ""


def test_dock_web_button_isolates_chrome_instance():
    import json as _json
    cfg_str, _ = engine.build_waybar_dock("nwg-drawer", "foot", "thunar",
                                          "google-chrome")
    cfg = _json.loads(cfg_str)
    click = cfg["custom/web"]["on-click"]
    assert "--ozone-platform=wayland" in click
    assert "--user-data-dir=" in click


def test_wallpaper_convert_cmd_has_text_and_output():
    cmd = engine.wallpaper_convert_cmd("convert", "/o/wp.png", "myhost",
                                       "10.0.0.5\nUbuntu")
    assert cmd[0] == "convert"
    assert cmd[-1] == "/o/wp.png"
    assert "myhost" in cmd and "10.0.0.5\nUbuntu" in cmd
    assert "xc:#1d2433" in cmd               # dark background fill
    assert "-annotate" in cmd


def test_wave_polylines_fill_canvas():
    lines = engine.wave_polylines(1920, 1080)
    assert len(lines) > 3                       # multiple bands tiled vertically
    assert all(p.startswith("polyline ") for p in lines)
    assert "1920," in lines[0]                  # spans the full width


def test_wallpaper_convert_cmd_draws_wave_field():
    cmd = engine.wallpaper_convert_cmd("convert", "/o/wp.png", "h", "s")
    assert "-draw" in cmd                        # wave polylines drawn
    assert "#2b303a" in cmd                      # subtle dark-grey wave colour
    assert cmd.index("-stroke") < cmd.index("-draw")   # stroke set before drawing


def test_build_wallpaper_falls_back_without_tool(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda n: None)   # no magick/convert
    assert engine.build_wallpaper(tmp_path / "wp.png", "h", "s") is False


def test_build_autostart_uses_wallpaper_image_when_set():
    sh = engine.build_autostart("/w/c", "/w/s", "/w/dc", "/w/ds",
                                wallpaper="/i/wallpaper.png")
    assert 'swaybg -i "/i/wallpaper.png" -m fill &' in sh
    assert "-c \"#1d2433\"" not in sh         # image replaces the flat colour


def test_write_seat_config_emits_all_files(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n in
                        ("nwg-drawer", "foot", "thunar", "firefox", "waybar",
                         "swaybg") else None)
    monkeypatch.setattr(engine, "scan_desktop_entries",
                        lambda *a: [("Firefox", "firefox")])
    monkeypatch.setattr(engine, "build_wallpaper", lambda *a: False)  # no convert in CI
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
    # bottom dock (second waybar) config + style
    assert "wlr/taskbar" in (wb / "dock-config").read_text()
    assert "#taskbar" in (wb / "dock-style.css").read_text()


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
