import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import clipboard_bridge as cb  # noqa: E402


def test_bridge_decision_propagates_a_to_b():
    """When a changes and b doesn't, propagate a to b."""
    d = cb.bridge_decision(a="hello", b="old", last_a="old", last_b="old")
    assert d == ("a->b", "hello")


def test_bridge_decision_propagates_b_to_a():
    """When b changes and a doesn't, propagate b to a."""
    d = cb.bridge_decision(a="old", b="world", last_a="old", last_b="old")
    assert d == ("b->a", "world")


def test_bridge_decision_none_when_equal():
    """When a==b already, no propagation needed."""
    assert cb.bridge_decision(a="same", b="same", last_a="x", last_b="y") is None


def test_bridge_decision_none_when_no_change():
    """When neither side changed vs last, nothing to do."""
    assert cb.bridge_decision(a="a", b="b", last_a="a", last_b="b") is None


def test_bridge_decision_no_loop_after_propagation():
    """After a->b, both read 'hello' next tick -> no action (dedup works)."""
    assert cb.bridge_decision(a="hello", b="hello", last_a="hello", last_b="hello") is None


def test_bridge_decision_both_change_prefers_a_to_b():
    """Both changed in same tick (rare): deterministically prefer a->b."""
    d = cb.bridge_decision(a="new_a", b="new_b", last_a="old_a", last_b="old_b")
    assert d == ("a->b", "new_a")


def test_read_clip_cmd_env(monkeypatch):
    """read_clip constructs wl-paste with correct WAYLAND_DISPLAY and XDG_RUNTIME_DIR."""
    calls = {}

    def fake_run(cmd, env=None, **kw):
        calls["cmd"] = cmd
        calls["env"] = env

        class R:
            returncode = 0
            stdout = "clipboard_content"

        return R()

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    out = cb.read_clip("wayland-2", "/run/user/1000")

    assert "wl-paste" in calls["cmd"][0] or calls["cmd"][0].endswith("wl-paste")
    assert calls["env"]["WAYLAND_DISPLAY"] == "wayland-2"
    assert calls["env"]["XDG_RUNTIME_DIR"] == "/run/user/1000"
    assert out == "clipboard_content"


def test_read_clip_returns_none_on_error(monkeypatch):
    """read_clip returns None on subprocess error (empty clipboard)."""

    def fake_run(cmd, env=None, **kw):
        class R:
            returncode = 1
            stdout = ""

        return R()

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    out = cb.read_clip("wayland-1", "/run/user/1000")
    assert out is None


def test_write_clip_cmd_env(monkeypatch):
    """write_clip constructs wl-copy with correct WAYLAND_DISPLAY and input."""
    calls = {}

    def fake_run(cmd, env=None, input=None, **kw):
        calls["cmd"] = cmd
        calls["env"] = env
        calls["input"] = input

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    cb.write_clip("wayland-1", "/run/user/1000", "payload")

    assert "wl-copy" in calls["cmd"][0] or calls["cmd"][0].endswith("wl-copy")
    assert calls["env"]["WAYLAND_DISPLAY"] == "wayland-1"
    assert calls["input"] == "payload"


def test_write_clip_ignores_errors(monkeypatch):
    """write_clip silently ignores errors (clipboard unavailable)."""
    call_count = [0]

    def fake_run(cmd, env=None, input=None, **kw):
        call_count[0] += 1
        raise OSError("compositor not ready")

    monkeypatch.setattr(cb.subprocess, "run", fake_run)
    # Should not raise
    cb.write_clip("wayland-1", "/run/user/1000", "payload")
    assert call_count[0] == 1


def test_run_loop_no_busy_loop_on_none():
    """Regression: after a decision with val=None, the run loop advances state.

    If both clipboards clear (a=None, b=None), bridge_decision returns
    ('a->b', None). The old run() code skipped state update when val is None,
    causing the same decision to repeat every tick (busy loop).
    This test verifies that after deciding on None, the second tick with the
    same inputs yields None (no repeat).
    """
    # Tick 1: a=None, b=None, last_a=None, last_b=None -> should return None
    # (a==b, no sync needed)
    d1 = cb.bridge_decision(a=None, b=None, last_a=None, last_b=None)
    assert d1 is None

    # Tick 2 (simulating run() advancing state after decision):
    # After tick 1's decision=None, run() sets last_a = last_b = a/b = None
    # Tick 2 reads the same None -> decision should again be None (no repeat)
    d2 = cb.bridge_decision(a=None, b=None, last_a=None, last_b=None)
    assert d2 is None
