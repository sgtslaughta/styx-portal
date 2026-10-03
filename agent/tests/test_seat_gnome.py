# agent/tests/test_seat_gnome.py
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seat_gnome  # noqa: E402


def test_launch_script_scrubs_display_and_sets_activation_env_before_exec():
    s = seat_gnome.build_launch_script(2560, 1440, "styx-seat", "/tmp/bus")
    lines = s.splitlines()
    unset = next(i for i, ln in enumerate(lines) if ln.startswith("unset DISPLAY WAYLAND_DISPLAY"))
    act = next(i for i, ln in enumerate(lines) if ln.startswith("dbus-update-activation-environment"))
    exe = next(i for i, ln in enumerate(lines) if ln.startswith("exec gnome-shell"))
    assert unset < act < exe
    assert "DISPLAY=" in lines[act] and "WAYLAND_DISPLAY=styx-seat-0" in lines[act]
    assert "PULSE_SINK=styx-seat" in lines[act]
    assert "export PULSE_SINK=styx-seat" in s
    assert "--virtual-monitor 2560x1440" in lines[exe]
    assert "--wayland-display=styx-seat-0" in lines[exe]
    assert "--unsafe-mode" not in s
    assert '> "/tmp/bus"' in s


def test_gnome_available_version_gate(monkeypatch):
    monkeypatch.setattr(seat_gnome.shutil, "which", lambda n: "/usr/bin/gnome-shell")
    for out, ok in (("GNOME Shell 46.0\n", True), ("GNOME Shell 47.2\n", True),
                    ("GNOME Shell 45.3\n", False)):
        monkeypatch.setattr(seat_gnome.subprocess, "run",
                            lambda *a, _o=out, **k: subprocess.CompletedProcess(a, 0, _o, ""))
        assert seat_gnome.gnome_available()[0] is ok
    monkeypatch.setattr(seat_gnome.shutil, "which", lambda n: None)
    assert seat_gnome.gnome_available() == (False, "gnome-shell not installed")


def test_ready_needs_socket_and_bus(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = type("P", (), {"poll": lambda self: None})()
    (tmp_path / "gnome-bus.addr").write_text("unix:path=/x\n")
    monkeypatch.setattr(seat, "_shell_answers", lambda: True)
    assert seat.ready(timeout=0.2) is False          # no socket yet
    (tmp_path / seat_gnome.SOCKET).touch()
    assert seat.ready(timeout=0.2) is True
    assert seat.info() == {"socket": "styx-seat-0", "bus": "unix:path=/x"}


def test_start_writes_script_and_counts_restarts(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.subprocess, "Popen",
                        lambda cmd, **k: calls.append((cmd, k)) or object())
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.start(1920, 1080)
    seat.start(1920, 1080)
    assert seat.restarts == 1
    cmd, kw = calls[0]
    assert cmd[:2] == ["dbus-run-session", "--"]
    assert Path(cmd[2]).read_text().startswith("#!/bin/bash")
    assert "DISPLAY" not in kw["env"] and "WAYLAND_DISPLAY" not in kw["env"]
