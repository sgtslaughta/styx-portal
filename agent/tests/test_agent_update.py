import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_update  # noqa: E402
import agent_updater as up  # noqa: E402

OLD = b'AGENT_VERSION = "0.9.30"\nprint("old")\n'
NEW = b'AGENT_VERSION = "0.9.31"\nprint("new")\n'


def _manifest(files, version="0.9.31", deps=None):
    return {"version": version, "deps": deps or {},
            "files": [{"remote": r, "local": loc, "sha256": hashlib.sha256(c).hexdigest(),
                       "size": len(c)} for r, loc, c in files]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "styx_agent.py").write_bytes(OLD)
    (inst / "health.py").write_bytes(b"def rollback(d):\n    return 0\n")
    cfg = {"server": "https://s", "agent_token": "t"}
    cfgp = tmp_path / "cfg.json"
    cfgp.write_text(json.dumps(cfg))
    calls = []
    monkeypatch.setattr(up, "_run", lambda cmd: calls.append(cmd) or (0, ""))
    monkeypatch.setattr(up, "GATE_TIMEOUT", 0.3)
    monkeypatch.setattr(up, "POLL_INTERVAL", 0.05)
    return inst, cfgp, calls


def _serve(monkeypatch, manifest, blobs):
    monkeypatch.setattr(up, "api", lambda cfg, path, payload=None: manifest)
    monkeypatch.setattr(up, "api_bytes",
                        lambda cfg, path: (blobs[path.rsplit("/", 1)[1]], "", ""))


def _state(inst):
    return json.loads((inst / "update-state.json").read_text())


def _argv(inst, cfgp, target="0.9.31"):
    return ["--install-dir", str(inst), "--config", str(cfgp), "--target", target]


def _confirm_soon(monkeypatch, inst):
    def sleep(_):
        s = _state(inst)
        s["state"] = "ok"
        up.write_state(inst, s)
    monkeypatch.setattr(up.time, "sleep", sleep)


def test_happy_path_swaps_and_backs_up(env, monkeypatch):
    inst, cfgp, calls = env
    m = _manifest([("agent.py", "styx_agent.py", NEW)])
    _serve(monkeypatch, m, {"agent.py": NEW})
    _confirm_soon(monkeypatch, inst)
    assert up.main(_argv(inst, cfgp)) == 0
    assert (inst / "styx_agent.py").read_bytes() == NEW
    b = list((inst / "backups").iterdir())
    assert len(b) == 1 and b[0].name.endswith("-0.9.30")
    assert (b[0] / "styx_agent.py").read_bytes() == OLD
    assert not (inst / ".update-staging").exists()
    assert ["systemctl", "--user", "restart", "styx-agent"] in calls
    assert _state(inst)["state"] == "ok"


def test_bad_sha_fails_untouched(env, monkeypatch):
    inst, cfgp, calls = env
    m = _manifest([("agent.py", "styx_agent.py", NEW)])
    _serve(monkeypatch, m, {"agent.py": NEW + b"#tampered\n"})
    assert up.main(_argv(inst, cfgp)) == 1
    assert (inst / "styx_agent.py").read_bytes() == OLD
    s = _state(inst)
    assert s["state"] == "failed" and "sha256" in s["error"]
    assert not (inst / ".update-staging").exists()
    assert calls == []


def test_py_compile_error_fails(env, monkeypatch):
    inst, cfgp, _ = env
    bad = b"def (:\n"
    _serve(monkeypatch, _manifest([("agent.py", "styx_agent.py", bad)]), {"agent.py": bad})
    assert up.main(_argv(inst, cfgp)) == 1
    assert (inst / "styx_agent.py").read_bytes() == OLD
    assert _state(inst)["state"] == "failed"


def test_manifest_version_mismatch_fails(env, monkeypatch):
    inst, cfgp, _ = env
    _serve(monkeypatch, _manifest([], version="0.9.99"), {})
    assert up.main(_argv(inst, cfgp)) == 1
    assert _state(inst)["state"] == "failed"


def test_gate_timeout_restores_byte_identical(env, monkeypatch):
    inst, cfgp, calls = env
    m = _manifest([("agent.py", "styx_agent.py", NEW)])
    _serve(monkeypatch, m, {"agent.py": NEW})
    monkeypatch.setattr(up, "_run", lambda cmd: calls.append(cmd) or (0, "boom line"))
    assert up.main(_argv(inst, cfgp)) == 1
    assert (inst / "styx_agent.py").read_bytes() == OLD
    s = _state(inst)
    assert s["state"] == "rolled_back"
    assert s["error"].startswith("new agent not healthy in 180 s: ") and len(s["error"]) <= 500
    assert calls.count(["systemctl", "--user", "restart", "styx-agent"]) == 2


def test_backups_pruned_to_three(env):
    inst, _, _ = env
    for n in range(5):
        (inst / "backups" / f"2026010100000{n}-0.9.{n}").mkdir(parents=True)
    up.prune_backups(inst)
    assert sorted(p.name for p in (inst / "backups").iterdir()) == [
        "20260101000002-0.9.2", "20260101000003-0.9.3", "20260101000004-0.9.4"]


def test_missing_dep_selects_full_mode(env):
    inst, _, _ = env
    sp = inst / "venv/lib/python3.12/site-packages"
    (sp / "selkies-2.1.0.dist-info").mkdir(parents=True)
    assert up.deps_missing(inst, {"selkies": "2.1.0"}) == []
    assert up.deps_missing(inst, {"selkies": "2.1.0", "pixelflux": "2.2.1"}) == ["pixelflux"]


def test_full_mode_failure_marks_failed(env, monkeypatch):
    inst, cfgp, calls = env
    _serve(monkeypatch, _manifest([], deps={"pixelflux": "9"}), {"script": b"#!/bin/bash\n"})
    monkeypatch.setattr(up, "_run", lambda cmd: calls.append(cmd) or (1, "nope"))
    assert up.main(_argv(inst, cfgp)) == 1
    assert _state(inst)["state"] == "failed"
    assert any(c[0] == "bash" and "--upgrade" in c for c in calls)


def test_confirm_flips_updating_to_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_update, "STATE", tmp_path / "s.json")
    agent_update.STATE.write_text(json.dumps({"state": "updating", "to": "0.9.31"}))
    agent_update.confirm("0.9.30")
    assert agent_update.report()["state"] == "updating"
    agent_update.confirm("0.9.31")
    assert agent_update.report()["state"] == "ok"


def test_report_none_without_state(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_update, "STATE", tmp_path / "none.json")
    assert agent_update.report() is None


def test_on_heartbeat_launches_unless_active(tmp_path, monkeypatch):
    runtime = tmp_path / "run"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    calls = []
    rc = {"active": 1}

    def fake(cmd):
        calls.append(cmd)
        return rc["active"] if "is-active" in cmd else 0
    monkeypatch.setattr(agent_update, "_run", fake)
    agent_update.on_heartbeat({}, {})
    assert calls == []
    agent_update.on_heartbeat({}, {"update": {"version": "0.9.31"}})
    assert (runtime / "styx-agent-updater.py").is_file()
    launch = calls[-1]
    assert launch[:2] == ["systemd-run", "--user"] and "--target" in launch
    assert launch[launch.index("--target") + 1] == "0.9.31"
    calls.clear()
    rc["active"] = 0
    agent_update.on_heartbeat({}, {"update": {"version": "0.9.31"}})
    assert len(calls) == 1 and "is-active" in calls[0]


def test_swap_keeps_exec_bit(tmp_path):
    inst, staging = tmp_path / "i", tmp_path / "s"
    inst.mkdir()
    staging.mkdir()
    (inst / "uninstall.sh").write_text("old")
    (inst / "uninstall.sh").chmod(0o755)
    (staging / "uninstall.sh").write_text("new")
    up.swap(inst, {"files": [{"local": "uninstall.sh"}]}, staging)
    assert (inst / "uninstall.sh").read_text() == "new"
    assert (inst / "uninstall.sh").stat().st_mode & 0o111
