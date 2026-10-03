"""run() supervisor wiring for the headless GNOME seat, driven by fakes.

No real subprocesses or gnome-shell: Popen, GnomeSeat, the portal API and the
clock are faked. Every run() is bounded by the fake heartbeat (revokes after a
scripted number of passes) and a runaway guard on the fake clock.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import styx_agent  # noqa: E402


class FakeProc:
    def __init__(self, h, cmd, **_):
        self.h = h
        self.kind = "selkies" if cmd[0].endswith("selkies") else "gateway"
        self.alive = True
        self.returncode = None
        h.events.append(("popen", self.kind))
        if len(h.events) > 200:
            raise RuntimeError("runaway run() loop")

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        if self.alive:
            self.h.events.append(("term", self.kind))
        self.alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.alive = False


class FakeSeat:
    def __init__(self, h):
        self.h, self.restarts, self._alive, self.started = h, 0, False, False
        self.size_file = h.tmp / "seat-size"

    def alive(self):
        return self._alive

    def start(self, w, h):
        if self.started:
            self.restarts += 1
        self.started = True
        self._alive = True
        self.h.events.append(("seat_start", w, h))

    def ready(self, timeout=20):
        return True

    def stop(self):
        self._alive = False
        self.h.events.append(("seat_stop",))

    def die(self):
        self._alive = False

    def info(self):
        return {"socket": "styx-seat-0", "bus": "unix:path=/x"}


class Harness:
    def __init__(self, tmp_path, monkeypatch, script, *,
                 starving_since=None, settings=None):
        self.events, self.payloads, self.passes = [], [], 0
        self.now, self.seat, self.script = 1_000_000.0, None, script
        self.tmp = tmp_path
        self.cfg = {
            "server": "https://x", "agent_token": "t", "workstation_id": "w",
            "port": 8443, "selkies_user": "u", "selkies_password": "p",
            "mode": "seat", "display": "",
            "stream_settings": settings or {"video_crf": 25, "seat_width": 2560,
                                            "seat_height": 1440},
            "install_dir": str(tmp_path), "ca_pin": "", "server_cert": ""}
        if starving_since is not None:
            (tmp_path / "gw_state.json").write_text(json.dumps({
                "active_connections": 1, "stream_starving": True,
                "starving_since": self.now + starving_since}))
        sg = styx_agent.seat_gnome
        monkeypatch.setattr(styx_agent.refit, "wait_for_request",
                            lambda path, timeout, **k: self.sleep(timeout))
        monkeypatch.setattr(sg, "gnome_available", lambda: (True, ""))

        def make_seat(*_a):
            self.seat = FakeSeat(self)
            return self.seat
        monkeypatch.setattr(sg, "GnomeSeat", make_seat)
        monkeypatch.setattr(styx_agent.subprocess, "Popen",
                            lambda cmd, **k: FakeProc(self, cmd, **k))
        monkeypatch.setattr(styx_agent.signal, "signal", lambda *a: None)
        monkeypatch.setattr(styx_agent.time, "time", lambda: self.now)
        monkeypatch.setattr(styx_agent.time, "monotonic", lambda: self.now)
        monkeypatch.setattr(styx_agent.time, "sleep", self.sleep)
        eng = styx_agent.engine
        monkeypatch.setattr(eng, "ensure_seat_sink", lambda: "styx-seat.monitor")
        monkeypatch.setattr(eng, "pick_dri_node", lambda: "")
        monkeypatch.setattr(eng, "build_selkies_cmd", lambda cfg, port, seat=None:
                            ([str(tmp_path / "venv/bin/selkies")], {}))
        monkeypatch.setattr(styx_agent, "LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(styx_agent, "CONFIG_PATH", tmp_path / "config.json")
        monkeypatch.setattr(styx_agent, "STATE_PATH", tmp_path / "state.json")
        monkeypatch.setattr(styx_agent, "api", self.api)

    def sleep(self, s):
        self.now += s
        if self.now > 1_000_000.0 + 3600:
            raise RuntimeError("runaway run() loop")

    def api(self, cfg, path, payload=None):
        self.passes += 1
        self.payloads.append(payload)
        if self.passes > 50:
            raise RuntimeError("runaway run() loop")
        ss = self.script(self, self.passes)
        if ss == "revoke":
            self.events.append(("revoke",))   # shutdown teardown follows
            return {"state": "revoked", "stream_settings": cfg["stream_settings"]}
        return {"state": "active",
                "stream_settings": ss if ss is not None else cfg["stream_settings"]}

    def run(self):
        return styx_agent.run(self.cfg)

    def live(self):
        """Events before shutdown teardown."""
        ev = self.events
        return ev[:ev.index(("revoke",))] if ("revoke",) in ev else ev

    def count(self, *ev):
        return sum(1 for e in self.live() if e[:len(ev)] == ev)


def _revoke_at(n):
    return lambda h, i: "revoke" if i >= n else None


def test_watchdog_restarts_selkies_then_escalates(tmp_path, monkeypatch):
    h = Harness(tmp_path, monkeypatch, _revoke_at(4), starving_since=0)
    assert h.run() == 0
    # First restart touches only selkies: no seat stop/start in between.
    i = h.events.index(("term", "selkies"))
    nxt = h.events.index(("popen", "selkies"), i)
    assert all(e[0] not in ("seat_stop", "seat_start") for e in h.events[i:nxt])
    # Grace period: starving stays >= 15s across passes with no elapsed time,
    # yet exactly 3 restarts happen (one per 30s heartbeat), escalating once.
    assert h.count("term", "selkies") == 3
    assert h.count("seat_stop") == 1                 # escalation (pre-shutdown)
    assert h.count("seat_start") == 2                # boot + post-escalation
    assert h.payloads[-1]["health"]["degraded"] is True
    assert h.payloads[-1]["health"]["seat_restarts"] == 1


def test_dead_gnome_shell_restarts_seat_then_selkies(tmp_path, monkeypatch):
    def script(h, i):
        if i == 1:
            h.seat.die()
        return "revoke" if i >= 2 else None
    h = Harness(tmp_path, monkeypatch, script)
    assert h.run() == 0
    i = h.events.index(("term", "selkies"))
    assert h.events[i + 1][0] == "seat_start"
    assert h.events[i + 2] == ("popen", "selkies")


def test_settings_push_restarts_seat_only_on_geometry(tmp_path, monkeypatch):
    def script(h, i):
        ss = h.cfg["stream_settings"]
        if i == 1:
            return {**ss, "video_crf": 30}
        if i == 2:
            assert h.count("seat_stop") == 0
            assert h.count("term", "selkies") == 1 and h.count("term", "gateway") == 1
            return {**ss, "seat_width": 1920}
        return "revoke"
    h = Harness(tmp_path, monkeypatch, script)
    assert h.run() == 0
    assert ("seat_start", 1920, 1440) in h.events
    assert h.count("seat_start") == 2


def test_seat_shell_flip_exits_for_restart(tmp_path, monkeypatch):
    def script(h, i):
        if i == 1:
            return {**h.cfg["stream_settings"], "seat_shell": "labwc"}
        pytest.fail("run() kept going after seat_shell changed")
    h = Harness(tmp_path, monkeypatch, script)
    assert h.run() != 0
    assert h.count("seat_stop") >= 1
    assert h.count("term", "selkies") == 1 and h.count("term", "gateway") == 1
