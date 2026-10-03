# agent/tests/test_seat_gnome.py
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seat_gnome  # noqa: E402


def test_launch_script_scrubs_display_and_sets_activation_env_before_exec():
    s = seat_gnome.build_launch_script("styx-seat", "/tmp/bus", "/p")
    lines = s.splitlines()
    unset = next(i for i, ln in enumerate(lines) if ln.startswith("unset DISPLAY WAYLAND_DISPLAY"))
    act = next(i for i, ln in enumerate(lines) if ln.startswith("dbus-update-activation-environment"))
    exe = next(i for i, ln in enumerate(lines) if ln.startswith("exec gnome-shell"))
    assert unset < act < exe
    assert "DISPLAY=" in lines[act] and "WAYLAND_DISPLAY=styx-seat-0" in lines[act]
    assert "PULSE_SINK=styx-seat" in lines[act]
    assert "export PULSE_SINK=styx-seat" in s
    assert "--wayland-display=styx-seat-0" in lines[exe]
    assert "--unsafe-mode" not in s
    assert '> /tmp/bus' in s
    assert "--virtual-monitor" not in s
    assert "export XDG_DESKTOP_PORTAL_DIR=/p" in s
    act = next(i for i, ln in enumerate(lines) if ln.startswith("dbus-update-activation-environment"))
    assert "XDG_DESKTOP_PORTAL_DIR=/p" in lines[act] and act < exe


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
    monkeypatch.setattr(seat, "_start_helper", lambda w, h: True)
    seat.size = (2560, 1440)
    assert seat.ready(timeout=0.2) is True
    assert seat.info() == {"socket": "styx-seat-0", "bus": "unix:path=/x"}


class _Dead:
    def poll(self):
        return 0


def test_start_writes_script_and_counts_restarts(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.subprocess, "Popen",
                        lambda cmd, **k: calls.append((cmd, k)) or _Dead())
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.start(1920, 1080)
    seat.start(1920, 1080)
    assert seat.restarts == 1
    cmd, kw = calls[0]
    assert cmd[:2] == ["dbus-run-session", "--"]
    assert Path(cmd[2]).read_text().startswith("#!/bin/bash")
    assert "DISPLAY" not in kw["env"] and "WAYLAND_DISPLAY" not in kw["env"]
    assert kw["env"]["XDG_RUNTIME_DIR"] == str(tmp_path)
    assert kw["start_new_session"] is True


class _P:
    pid = 4242

    def __init__(self, timeout=False):
        self.timeout, self.waits = timeout, 0

    def poll(self):
        return None

    def wait(self, timeout=None):
        self.waits += 1
        if self.timeout and timeout is not None:
            raise subprocess.TimeoutExpired("x", timeout)


def test_stop_kills_process_group(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.os, "killpg", lambda *a: calls.append(a))
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = _P()
    seat.stop()
    assert calls == [(4242, signal.SIGTERM)]
    seat._proc = _P(timeout=True)
    calls.clear()
    seat.stop()
    assert calls == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]


def test_stop_tolerates_dead_group(tmp_path, monkeypatch):
    def gone(*a):
        raise ProcessLookupError
    monkeypatch.setattr(seat_gnome.os, "killpg", gone)
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = _P()
    seat.stop()
    assert seat._proc is None


def test_start_cleans_stale_socket_and_stops_live(tmp_path, monkeypatch):
    monkeypatch.setattr(seat_gnome.subprocess, "Popen", lambda cmd, **k: object())
    for n in (seat_gnome.SOCKET, seat_gnome.SOCKET + ".lock"):
        (tmp_path / n).touch()
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    stopped = []
    monkeypatch.setattr(seat, "alive", lambda: True)
    monkeypatch.setattr(seat, "stop", lambda: stopped.append(1))
    seat.start(1920, 1080)
    assert stopped == [1]
    assert not (tmp_path / seat_gnome.SOCKET).exists()
    assert not (tmp_path / (seat_gnome.SOCKET + ".lock")).exists()


def test_shell_probe_timeout_is_not_ready(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired("gdbus", 5)
    monkeypatch.setattr(seat_gnome.subprocess, "run", boom)
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = type("P", (), {"poll": lambda self: None})()
    (tmp_path / "gnome-bus.addr").write_text("unix:path=/x\n")
    (tmp_path / seat_gnome.SOCKET).touch()
    assert seat.ready(timeout=0.2) is False


def test_write_portal_dir_routes_screencast_and_remote_desktop_to_styx(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "gnome.portal").write_text("[portal]\n")
    d = tmp_path / "portals"
    seat_gnome.write_portal_dir(d, src)
    seat_gnome.write_portal_dir(d, src)                       # idempotent
    assert (d / "gnome.portal").exists()
    assert "DBusName=org.freedesktop.impl.portal.desktop.styx" in (d / "styx.portal").read_text()
    for n in ("portals.conf", "ubuntu-portals.conf", "gnome-portals.conf"):
        t = (d / n).read_text()
        assert "org.freedesktop.impl.portal.ScreenCast=styx;" in t
        assert "org.freedesktop.impl.portal.RemoteDesktop=styx;" in t


def _fake_proc(rc=None):
    return type("P", (), {"poll": lambda self: rc, "pid": 0})()


def test_refit_success_persists_size(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.bus = "unix:path=/b"

    def spawn(w, h):
        seat.ready_file.write_text(f"{w}x{h}")
        return _fake_proc()
    monkeypatch.setattr(seat, "_spawn_helper", spawn)
    monkeypatch.setattr(seat, "_stop_helper", lambda: None)
    assert seat.refit(2552, 1294) is True
    assert seat.size == (2552, 1294)
    assert (tmp_path / "seat-size").read_text() == "2552x1294"


def test_refit_failure_restores_previous_size(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.bus = "unix:path=/b"
    seat.size = (1920, 1080)
    calls = []

    def spawn(w, h):
        calls.append((w, h))
        if (w, h) == (1920, 1080):
            seat.ready_file.write_text("1920x1080")
            return _fake_proc()
        return _fake_proc(rc=1)                                # helper died
    monkeypatch.setattr(seat, "_spawn_helper", spawn)
    monkeypatch.setattr(seat, "_stop_helper", lambda: None)
    assert seat.refit(2552, 1294) is False
    assert calls == [(2552, 1294), (1920, 1080)]
    assert seat.size == (1920, 1080)


def test_alive_requires_helper_once_started(tmp_path):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = _fake_proc()
    assert seat.alive() is True                               # helper not started yet
    seat._helper = _fake_proc(rc=1)
    assert seat.alive() is False


def test_gnome_available_reports_missing_helper_deps(monkeypatch):
    monkeypatch.setattr(seat_gnome.shutil, "which", lambda n: "/usr/bin/gnome-shell")

    def run(cmd, *a, **k):
        if cmd[0] == "gnome-shell":
            return subprocess.CompletedProcess(cmd, 0, "GNOME Shell 46.0\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", "ModuleNotFoundError")
    monkeypatch.setattr(seat_gnome.subprocess, "run", run)
    ok, why = seat_gnome.gnome_available()
    assert ok is False and "python3-dbus" in why


def test_dead_helper_heals_without_restarting_gnome(tmp_path, monkeypatch):
    """GNOME's screen-share Stop kills only the virtual monitor: keep GNOME."""
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = _fake_proc()                 # GNOME alive
    seat._helper = _fake_proc(rc=1)           # helper died
    seat.size = (2434, 1262)
    assert seat.alive() is False

    def no_popen(*a, **k):
        raise AssertionError("GNOME must not be restarted")
    monkeypatch.setattr(seat_gnome.subprocess, "Popen", no_popen)
    started = []
    monkeypatch.setattr(seat, "_start_helper", lambda w, h: started.append((w, h)) or True)
    seat.start(2434, 1262)
    assert seat.ready() is True and started == [(2434, 1262)]
    assert seat.restarts == 0
