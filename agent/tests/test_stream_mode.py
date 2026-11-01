"""Viewer transport pick survives selkies restarts."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_procs  # noqa: E402
import engine  # noqa: E402


def _cfg(tmp_path, transport="websockets"):
    return {"install_dir": str(tmp_path), "stream_settings": {"transport": transport}}


def _mode(cmd):
    return next(a for a in cmd if a.startswith("--mode="))


def _build(cfg):
    with mock.patch.object(engine.bundle_patch, "apply"):
        return engine.build_selkies_cmd(cfg, 1, {"socket": "s", "bus": "b"})[0]


def test_file_overrides_transport(tmp_path):
    (tmp_path / "stream-mode").write_text("webrtc")
    assert _mode(_build(_cfg(tmp_path))) == "--mode=webrtc"


def test_missing_or_invalid_file_falls_back(tmp_path):
    assert _mode(_build(_cfg(tmp_path, "webrtc"))) == "--mode=webrtc"
    (tmp_path / "stream-mode").write_text("junk")
    assert _mode(_build(_cfg(tmp_path, "websockets"))) == "--mode=websockets"


def test_mode_change_restarts_standby(tmp_path):
    state = tmp_path / "gw_state.json"
    standby = mock.Mock()
    procs = {"standby": standby}
    with mock.patch.object(agent_procs, "_terminate") as term:
        assert agent_procs.sync_stream_mode(state, procs, None) is None
        (tmp_path / "stream-mode").write_text("webrtc")
        procs["standby"] = standby
        term.reset_mock()
        assert agent_procs.sync_stream_mode(state, procs, None) == "webrtc"
        term.assert_called_once_with(standby, timeout=0)
        assert procs["standby"] is None
        procs["standby"] = standby
        term.reset_mock()
        assert agent_procs.sync_stream_mode(state, procs, "webrtc") == "webrtc"
        term.assert_not_called()
        assert procs["standby"] is standby


def test_portal_transport_change_clears_file(tmp_path):
    state = tmp_path / "gw_state.json"
    f = tmp_path / "stream-mode"
    f.write_text("webrtc")
    assert not agent_procs.clear_stream_mode_on_portal_change(
        state, {"transport": "websockets", "x": 1}, {"transport": "websockets", "x": 2})
    assert f.exists()
    assert agent_procs.clear_stream_mode_on_portal_change(
        state, {"transport": "websockets"}, {"transport": "webrtc"})
    assert not f.exists()
