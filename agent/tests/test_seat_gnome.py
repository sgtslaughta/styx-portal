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
    assert "DISPLAY=" in lines[act] and "WAYLAND_DISPLAY=wayland-70" in lines[act]
    assert "PULSE_SINK=styx-seat" in lines[act]
    assert "export PULSE_SINK=styx-seat" in s
    assert "--no-x11" not in lines[exe]   # Xwayland on demand for X11 apps (Steam)
    pc = next(i for i, ln in enumerate(lines) if ln.startswith("export PULSE_CLIENTCONFIG="))
    assert pc < exe and "auto-connect-display = no" in s   # else libpulse deadlocks the shell
    assert "--wayland-display=wayland-70" in lines[exe]
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
    assert seat.info() == {"socket": "wayland-70", "bus": "unix:path=/x", "x11": "on"}


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


def test_helper_gets_scale_file_env(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.subprocess, "Popen",
                        lambda cmd, **k: calls.append((cmd, k)) or object())
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._spawn_helper(1920, 1080)
    assert calls[0][1]["env"]["STYX_SEAT_SCALE_FILE"] == str(tmp_path / "seat-scale")


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
    assert calls == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]
    seat._proc = _P(timeout=True)
    calls.clear()
    seat.stop()
    assert calls == [(4242, signal.SIGTERM), (4242, signal.SIGKILL), (4242, signal.SIGKILL)]


def test_stop_sigkills_group_even_when_leader_exits_after_sigterm(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.os, "killpg", lambda *a: calls.append(a))
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    p = _P()
    seat._proc = p
    seat.stop()
    assert calls[-1] == (4242, signal.SIGKILL) and p.waits == 1


def test_stop_sigkill_ignores_missing_group(tmp_path, monkeypatch):
    def killpg(pg, sig):
        if sig == signal.SIGKILL:
            raise ProcessLookupError
    monkeypatch.setattr(seat_gnome.os, "killpg", killpg)
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._proc = _P()
    seat.stop()
    assert seat._proc is None


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


def test_healthy_needs_live_proc_and_answering_shell(tmp_path, monkeypatch):
    """Watchdog escalation gate: a frameless viewer on a healthy seat is a
    client/stream problem, not a reason to restart GNOME (and its apps)."""
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    monkeypatch.setattr(seat, "alive", lambda: True)
    monkeypatch.setattr(seat, "_shell_answers", lambda: True)
    assert seat.healthy()
    monkeypatch.setattr(seat, "_shell_answers", lambda: False)   # main loop wedged
    assert not seat.healthy()
    monkeypatch.setattr(seat, "alive", lambda: False)
    monkeypatch.setattr(seat, "_shell_answers", lambda: True)
    assert not seat.healthy()


def test_helper_gets_max_fps_arg(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.subprocess, "Popen",
                        lambda cmd, **k: calls.append(cmd) or object())
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat._spawn_helper(1920, 1080)
    assert calls[0][-2:] == ["--max-fps", "60"]
    seat.fps = 120
    seat._spawn_helper(1920, 1080)
    assert calls[1][-2:] == ["--max-fps", "120"]


def test_restart_helper_applies_new_fps_without_touching_shell(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.size = (1920, 1080)
    calls = []
    monkeypatch.setattr(seat, "_start_helper", lambda w, h: calls.append((w, h, seat.fps)) or True)
    assert seat.restart_helper(120) is True and calls == [(1920, 1080, 120)]
    seat.size = None
    assert seat.restart_helper(60) is False


def test_restart_helper_failure_retries_old_fps(tmp_path, monkeypatch):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.size, seat.fps = (1920, 1080), 60
    calls = []
    monkeypatch.setattr(seat, "_start_helper",
                        lambda w, h: calls.append(seat.fps) or len(calls) > 1)
    assert seat.restart_helper(120) is False
    assert calls == [120, 60] and seat.fps == 60


def _seat_with_version(tmp_path, monkeypatch, ver="GNOME Shell 50.1"):
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    monkeypatch.setattr(seat_gnome, "gnome_version", lambda: ver)
    monkeypatch.setattr(seat_gnome.subprocess, "Popen", lambda cmd, **k: _Dead())
    return seat


def test_shell_probe_uses_main_loop_property_get(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seat_gnome.subprocess, "run",
                        lambda cmd, **k: calls.append((cmd, k)) or type("R", (), {"returncode": 0})())
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    seat.bus = "unix:path=/x"
    assert seat._shell_answers() is True
    cmd, kw = calls[0]
    assert cmd == ["gdbus", "call", "--session", "-d", "org.gnome.Shell", "-o",
                   "/org/gnome/Shell", "-m", "org.freedesktop.DBus.Properties.Get",
                   "org.gnome.Shell", "ShellVersion"]
    assert kw["timeout"] == 5 and kw["env"]["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/x"


def test_launch_script_no_x11_flag():
    on = seat_gnome.build_launch_script("s", "/b", "/p")
    off = seat_gnome.build_launch_script("s", "/b", "/p", x11=False)
    exe_on = next(ln for ln in on.splitlines() if "exec gnome-shell" in ln)
    exe_off = next(ln for ln in off.splitlines() if "exec gnome-shell" in ln)
    assert "--no-x11" not in exe_on and "--no-x11" in exe_off
    assert "export PULSE_CLIENTCONFIG=" in off


def test_marker_with_current_version_turns_x11_off(tmp_path, monkeypatch):
    seat = _seat_with_version(tmp_path, monkeypatch)
    (tmp_path / "seat-no-x11").write_text("GNOME Shell 50.1|eager\n")
    seat.start(1920, 1080)
    assert "--no-x11" in seat.script.read_text()
    assert "LD_PRELOAD" not in seat.script.read_text()
    assert seat.info()["x11"] == "fallback"


def test_marker_with_other_version_keeps_x11_on(tmp_path, monkeypatch):
    seat = _seat_with_version(tmp_path, monkeypatch)
    (tmp_path / "seat-no-x11").write_text("GNOME Shell 49.0\n")
    seat.start(1920, 1080)
    assert "--no-x11" not in seat.script.read_text()
    assert seat.info()["x11"] == "on"


def test_x11_mode_off_disables_without_marker(tmp_path, monkeypatch):
    seat = _seat_with_version(tmp_path, monkeypatch)
    seat.x11_mode = "off"
    seat.start(1920, 1080)
    assert "--no-x11" in seat.script.read_text()
    assert seat.info()["x11"] == "off"
    monkeypatch.setattr(seat, "alive", lambda: True)
    monkeypatch.setattr(seat, "_shell_answers", lambda: False)
    assert not seat.healthy()
    assert not (tmp_path / "seat-no-x11").exists()


def test_unhealthy_while_alive_with_x11_writes_marker(tmp_path, monkeypatch, capsys):
    seat = _seat_with_version(tmp_path, monkeypatch)
    seat.start(1920, 1080)
    assert seat.info()["x11"] == "on" and seat.x11_on
    monkeypatch.setattr(seat, "alive", lambda: True)
    monkeypatch.setattr(seat, "_shell_answers", lambda: False)
    for _ in range(seat_gnome.STRIKES - 1):        # a busy shell: not yet a deadlock
        assert not seat.healthy()
        assert not (tmp_path / "seat-no-x11").exists() and not seat.fell_back
    assert not seat.healthy()
    assert seat.fell_back
    assert (tmp_path / "seat-no-x11").read_text().strip() == "GNOME Shell 50.1|eager"
    assert seat.info()["x11"] == "fallback"
    assert "falling back to --no-x11" in capsys.readouterr().out


def test_ready_timeout_with_x11_writes_marker(tmp_path, monkeypatch):
    seat = _seat_with_version(tmp_path, monkeypatch)
    seat.start(1920, 1080)
    seat._proc = type("P", (), {"poll": lambda self: None})()
    seat._helper = None
    assert seat.ready(timeout=0.2) is False          # slow start: no bus/socket yet
    assert not (tmp_path / "seat-no-x11").exists()
    seat.bus_file.write_text("unix:path=/x")         # up, but main loop never answers
    (tmp_path / seat_gnome.SOCKET).touch()
    monkeypatch.setattr(seat, "_shell_answers", lambda: False)
    assert seat.ready(timeout=0.2) is False
    assert (tmp_path / "seat-no-x11").exists()


def test_stop_escalates_to_sigkill_within_seconds(tmp_path, monkeypatch):
    waits = []
    seat = seat_gnome.GnomeSeat(tmp_path, str(tmp_path), log=subprocess.DEVNULL)
    monkeypatch.setattr(seat_gnome.os, "killpg", lambda *a: None)

    class P(_P):
        def wait(self, timeout=None):
            waits.append(timeout)
            if timeout is not None:
                raise subprocess.TimeoutExpired("x", timeout)
    seat._proc = P()
    seat.stop()
    assert waits[0] <= 5


def test_old_format_marker_is_ignored_and_x11_retried_eager(tmp_path, monkeypatch):
    seat = _seat_with_version(tmp_path, monkeypatch)
    (tmp_path / "seat-no-x11").write_text("GNOME Shell 50.1\n")
    seat.start(1920, 1080)
    assert seat.x11_on and "--no-x11" not in seat.script.read_text()


def test_launch_script_preloads_eager_lib_when_x11_on(tmp_path, monkeypatch):
    seat = _seat_with_version(tmp_path, monkeypatch)
    seat.start(1920, 1080)
    so = tmp_path / "libstyx-xwl-eager.so"
    assert so.read_bytes().startswith(b"\x7fELF")
    line = next(ln for ln in seat.script.read_text().splitlines() if "exec gnome-shell" in ln)
    assert line.startswith(f"LD_PRELOAD={so} exec gnome-shell")


def test_launch_script_preload_path_is_quoted():
    s = seat_gnome.build_launch_script("s", "/b", "/p", preload="/a b/x.so")
    assert "LD_PRELOAD='/a b/x.so' exec gnome-shell" in s
    assert "LD_PRELOAD" not in seat_gnome.build_launch_script("s", "/b", "/p", x11=False)
