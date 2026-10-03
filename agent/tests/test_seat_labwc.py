import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seat_labwc  # noqa: E402


def test_pick_launcher_prefers_grid_then_fuzzel(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n == "nwg-drawer" else None)
    assert seat_labwc.pick_launcher() == "nwg-drawer"
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/fuzzel" if n == "fuzzel" else None)
    assert seat_labwc.pick_launcher() == "fuzzel"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert seat_labwc.pick_launcher() == ""


def test_pick_file_manager_detection_order(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n in ("thunar", "nemo") else None)
    # nemo ranks above thunar in the order
    assert seat_labwc.pick_file_manager() == "nemo"
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert seat_labwc.pick_file_manager() == ""


def test_scan_desktop_entries_parses_and_filters(tmp_path):
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "firefox.desktop").write_text(
        "[Desktop Entry]\nName=Firefox\nExec=firefox %u\nType=Application\n")
    (apps / "hidden.desktop").write_text(
        "[Desktop Entry]\nName=Secret\nExec=secret\nNoDisplay=true\n")
    (apps / "noexec.desktop").write_text(
        "[Desktop Entry]\nName=Broken\nType=Application\n")
    entries = seat_labwc.scan_desktop_entries([str(apps)])
    assert entries == [("Firefox", "firefox")]   # field code stripped, others filtered


def test_scan_desktop_entries_skips_missing_dirs():
    assert seat_labwc.scan_desktop_entries(["/no/such/dir"]) == []


def test_build_root_menu_includes_files_apps_and_escapes(tmp_path):
    xml = seat_labwc.build_root_menu(
        [("Rofi & Co", "rofi"), ("Term", "xterm")],
        term="foot", file_mgr="thunar", home="/home/u")
    assert "<action name=\"Execute\" command=\"thunar /home/u\"/>" in xml
    assert "Files" in xml
    assert "Rofi &amp; Co" in xml          # XML-escaped label
    assert "<action name=\"Exit\"/>" in xml
    assert "Applications" in xml


def test_build_root_menu_escapes_command_attribute():
    xml = seat_labwc.build_root_menu([("App", "run & thing")],
                                 term="", file_mgr="", home="/h")
    assert "run &amp; thing" in xml


def test_build_root_menu_without_file_manager():
    xml = seat_labwc.build_root_menu([], term="foot", file_mgr="", home="/home/u")
    assert "Files" not in xml
    assert "foot" in xml                    # Terminal entry still present


def test_build_waybar_config_has_tray_and_menu(monkeypatch):
    import json as _json
    cfg_str, style = seat_labwc.build_waybar_config("nwg-drawer")
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
    cfg_str, _ = seat_labwc.build_waybar_config("")
    import json as _json
    assert _json.loads(cfg_str)["custom/menu"]["on-click"] == "true"


def test_build_labwc_rc_binds_super_to_launcher():
    rc = seat_labwc.build_labwc_rc("nwg-drawer", "foot")
    assert 'key="W-d"' in rc and "nwg-drawer" in rc
    assert 'key="W-Return"' in rc and "foot" in rc


def test_build_labwc_rc_no_launcher_is_noop_command():
    rc = seat_labwc.build_labwc_rc("", "foot")
    assert 'command="true"' in rc            # Super bound to a harmless no-op


def test_build_labwc_environment_forces_dark():
    env = seat_labwc.build_labwc_environment()
    assert "GTK_THEME=Adwaita-dark" in env
    assert "XCURSOR_THEME=Adwaita" in env


def test_build_autostart_emits_guarded_lines():
    sh = seat_labwc.build_autostart(
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
    cfg_str, style = seat_labwc.build_waybar_dock("nwg-drawer", "foot", "thunar",
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
    cfg_str, _ = seat_labwc.build_waybar_dock("", "", "", "")
    cfg = _json.loads(cfg_str)
    assert cfg["modules-center"] == ["wlr/taskbar"]    # no pins when nothing found


def test_browser_launch_cmd_chrome_isolates_instance_and_forces_wayland():
    # A chrome already running in the user's :0/VNC session owns the shared
    # profile's singleton, so a plain launch just opens a window THERE. A
    # dedicated --user-data-dir gives the seat its own instance; --ozone forces
    # it onto the Wayland seat instead of $DISPLAY (=:0, the VNC server).
    for browser in ("google-chrome", "chromium", "chromium-browser"):
        cmd = seat_labwc.browser_launch_cmd(browser)
        assert cmd.startswith(f"{browser} ")
        assert "--ozone-platform=wayland" in cmd
        assert "--user-data-dir=" in cmd
        assert "styx-seat" in cmd          # a separate, seat-only profile dir


def test_browser_launch_cmd_firefox_isolates_instance():
    # Same singleton trap for Firefox: --no-remote + a dedicated profile force a
    # new instance rather than routing to a :0-session Firefox. Wayland comes
    # from MOZ_ENABLE_WAYLAND in the labwc environment file.
    cmd = seat_labwc.browser_launch_cmd("firefox")
    assert cmd.startswith("firefox ")
    assert "--no-remote" in cmd
    assert "--profile" in cmd
    assert seat_labwc.browser_launch_cmd("") == ""


def test_dock_web_button_isolates_chrome_instance():
    import json as _json
    cfg_str, _ = seat_labwc.build_waybar_dock("nwg-drawer", "foot", "thunar",
                                          "google-chrome")
    cfg = _json.loads(cfg_str)
    click = cfg["custom/web"]["on-click"]
    assert "--ozone-platform=wayland" in click
    assert "--user-data-dir=" in click


def test_wallpaper_convert_cmd_has_text_and_output():
    cmd = seat_labwc.wallpaper_convert_cmd("convert", "/o/wp.png", "myhost",
                                       "10.0.0.5\nUbuntu")
    assert cmd[0] == "convert"
    assert cmd[-1] == "/o/wp.png"
    assert "myhost" in cmd and "10.0.0.5\nUbuntu" in cmd
    assert "xc:#1d2433" in cmd               # dark background fill
    assert "-annotate" in cmd


def test_accent_colors_deterministic_unique_and_dark():
    a = seat_labwc.accent_colors("ws-alice")
    assert a == seat_labwc.accent_colors("ws-alice")     # stable across calls
    assert a != seat_labwc.accent_colors("ws-bob")       # unique per hostname
    base, wave = a
    assert base.startswith("#") and len(base) == 7
    assert wave.startswith("#") and len(wave) == 7
    r, g, b = (int(base[i:i + 2], 16) for i in (1, 3, 5))
    assert 0.299 * r + 0.587 * g + 0.114 * b < 90    # dark: white text readable
    wr, wg, wb = (int(wave[i:i + 2], 16) for i in (1, 3, 5))
    assert wr + wg + wb > r + g + b                  # waves lighter than base


def test_build_wallpaper_tints_by_hostname(tmp_path, monkeypatch):
    import shutil
    import subprocess
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        (tmp_path / "wp.png").write_bytes(b"x")
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(shutil, "which", lambda _t: "convert")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert seat_labwc.build_wallpaper(tmp_path / "wp.png", "ws-alice", "sub") is True
    base, wave = seat_labwc.accent_colors("ws-alice")
    assert f"xc:{base}" in captured["cmd"]            # base field tinted by host
    assert wave in captured["cmd"]                    # wave colour matches


def test_wave_polylines_fill_canvas():
    lines = seat_labwc.wave_polylines(1920, 1080)
    assert len(lines) > 3                       # multiple bands tiled vertically
    assert all(p.startswith("polyline ") for p in lines)
    assert "1920," in lines[0]                  # spans the full width


def test_wallpaper_convert_cmd_draws_wave_field():
    cmd = seat_labwc.wallpaper_convert_cmd("convert", "/o/wp.png", "h", "s")
    assert "-draw" in cmd                        # wave polylines drawn
    assert "#2b303a" in cmd                      # subtle dark-grey wave colour
    assert cmd.index("-stroke") < cmd.index("-draw")   # stroke set before drawing


def test_build_wallpaper_falls_back_without_tool(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda n: None)   # no magick/convert
    assert seat_labwc.build_wallpaper(tmp_path / "wp.png", "h", "s") is False


def test_build_autostart_uses_wallpaper_image_when_set():
    sh = seat_labwc.build_autostart("/w/c", "/w/s", "/w/dc", "/w/ds",
                                wallpaper="/i/wallpaper.png")
    assert 'swaybg -i "/i/wallpaper.png" -m fill &' in sh
    assert "-c \"#1d2433\"" not in sh         # image replaces the flat colour


def test_write_seat_config_emits_all_files(tmp_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/" + n if n in
                        ("nwg-drawer", "foot", "thunar", "firefox", "waybar",
                         "swaybg") else None)
    monkeypatch.setattr(seat_labwc, "scan_desktop_entries",
                        lambda *a: [("Firefox", "firefox")])
    monkeypatch.setattr(seat_labwc, "build_wallpaper", lambda *a: False)  # no convert in CI
    labwc = tmp_path / "install" / "labwc"
    seat_labwc.write_seat_config(labwc)
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
    monkeypatch.setattr(seat_labwc, "scan_desktop_entries", lambda *a: [])
    labwc = tmp_path / "install" / "labwc"
    seat_labwc.write_seat_config(labwc)                          # must not raise
    # launcher empty -> menu on-click is the no-op
    import json as _json
    cfg = _json.loads((tmp_path / "install" / "waybar" / "config").read_text())
    assert cfg["custom/menu"]["on-click"] == "true"
