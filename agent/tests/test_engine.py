import json
import sys
from pathlib import Path

import pytest

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


def _flags(cmd):
    return {a.split("=", 1)[0] for a in cmd if a.startswith("--")}


def _stub(monkeypatch, dri="", monitor="", hw=()):
    monkeypatch.setattr(engine, "pick_dri_node", lambda: dri)
    monkeypatch.setattr(engine, "hw_encoders", lambda node: hw)
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: monitor)
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, x: (1920, 1080))


def test_mirror_cmd_is_x11_with_fixed_size(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "out.monitor")
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: "/tmp/xa")
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, x: (2560, 1440))
    cmd, env = engine.build_selkies_cmd(cfg, 18444)
    assert cmd[0].endswith("venv/bin/selkies")
    assert "--port=18444" in cmd and "--enable-basic-auth=false" in cmd
    assert "--manual-width=2560" in cmd and "--manual-height=1440" in cmd
    assert "--encode-dri=/dev/dri/renderD128" in cmd and "--render-dri=/dev/dri/renderD128" in cmd
    assert "--wayland=true" not in cmd
    assert env["DISPLAY"] == ":1" and env["XAUTHORITY"] == "/tmp/xa"
    assert "--control-port" not in _flags(cmd) and "--dri-node" not in _flags(cmd)
    assert not any("pw" in a for a in cmd)


def test_gnome_seat_cmd_targets_host_display(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "x.monitor")
    seat = {"socket": "wayland-70", "bus": "unix:path=/tmp/bus"}
    cmd, env = engine.build_selkies_cmd(cfg, 18444, seat)
    assert "--wayland=true" in cmd
    assert "--wayland-host-display=wayland-70" in cmd
    assert cmd[1].endswith("engine.py")    # clipboard shim launcher
    assert env["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/tmp/bus"
    assert env["XDG_CURRENT_DESKTOP"] == "ubuntu:GNOME"
    assert "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env
    assert "--audio-device-name=styx-seat.monitor" in cmd
    assert not any(a.startswith("--wayland-socket-index") for a in cmd)


def test_labwc_seat_cmd_uses_own_compositor(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg, 18444)
    assert "--wayland=true" in cmd
    assert not any(a.startswith("--wayland-host-display") for a in cmd)
    assert "SELKIES_USE_CPU" not in env and env["SELKIES_AUDIO_ENABLED"] == "false"
    assert "--wayland-socket-index=1" in cmd


def test_labwc_seat_cmd_uses_persisted_socket_index(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, mode="seat", display="", seat_socket_index=3)
    _stub(monkeypatch)
    cmd, _ = engine.build_selkies_cmd(cfg, 18444)
    assert "--wayland-socket-index=3" in cmd


def test_features_off_until_their_phase(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _stub(monkeypatch)
    cmd, _ = engine.build_selkies_cmd(cfg, 1)
    for f in ("--printing-enabled=false|locked", "--microphone-enabled=false|locked",
              "--webcam-enabled=false|locked", "--gamepad-enabled=false|locked",
              "--video-10bit=false|locked"):
        assert f in cmd


def test_quality_env_prefers_video_keys_and_keeps_old(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={"h264_crf": 22, "video_paintover_crf": 18,
                                          "video_streaming_mode": True})
    _stub(monkeypatch)
    _, env = engine.build_selkies_cmd(cfg, 1)
    assert env["SELKIES_VIDEO_CRF"] == "22"
    assert env["SELKIES_VIDEO_PAINTOVER_CRF"] == "18"
    assert env["SELKIES_VIDEO_STREAMING_MODE"] == "true"


def test_quality_env_ignores_bad_values(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={"video_crf": "abc", "video_paintover_crf": 999})
    _stub(monkeypatch)
    _, env = engine.build_selkies_cmd(cfg, 1)
    assert "SELKIES_VIDEO_CRF" not in env
    assert env["SELKIES_VIDEO_PAINTOVER_CRF"] == "12"          # bad value -> default
    assert env["SELKIES_VIDEO_STREAMING_MODE"] == "false"   # 2.0 default is true; keep ours
    assert env["SELKIES_VIDEO_FULLCOLOR"] == "false"         # 4:4:4 is opt-in (software x264 on VA-API)


def test_every_flag_exists_in_installed_selkies(tmp_path, monkeypatch):
    """2.0 only WARNS on unknown flags, so a renamed flag would silently no-op."""
    import importlib.util
    import re
    spec = importlib.util.find_spec("selkies")
    if spec is None or not spec.submodule_search_locations:
        pytest.skip("selkies 2.0 not installed in this venv")
    src = Path(list(spec.submodule_search_locations)[0], "settings.py").read_text()
    known = set(re.findall(r'"name":\s*"([a-z0-9_]+)"', src))
    cfg = _cfg(tmp_path, mode="seat", display="")
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "/dev/dri/renderD128")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "m")
    cmd, _ = engine.build_selkies_cmd(cfg, 1, {"socket": "s", "bus": "b"})
    for flag in _flags(cmd):
        assert flag[2:].replace("-", "_") in known, flag


def test_audio_disabled_when_no_pulse(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(engine, "query_display_geometry", lambda d, xa: (1920, 1080))
    monkeypatch.setattr(engine, "_find_xauthority", lambda c: None)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    cmd, env = engine.build_selkies_cmd(cfg, 18444)
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


_SEQ = __import__("itertools").count()


def _seat_cmd(tmp_path, monkeypatch, ss, seat=None, mode="seat"):
    sub = tmp_path / str(next(_SEQ))
    sub.mkdir()
    cfg = _cfg(sub, mode=mode, display="", stream_settings=ss)
    monkeypatch.setattr(engine, "pick_dri_node", lambda: "")
    monkeypatch.setattr(engine, "resolve_monitor_source", lambda: "")
    return engine.build_selkies_cmd(cfg, 1, seat)[0]


def test_bitrate_is_viewer_adjustable_ceiling(tmp_path, monkeypatch):
    """Admin bitrate is the default AND the ceiling; viewers may lower it.
    Floor is min(1000, kbps) so a stale 1.x value of 8 (Mbps) cannot mean 8 kbps."""
    cmd = _seat_cmd(tmp_path, monkeypatch, {"video_bitrate_kbps": 20000})
    assert "--video-bitrate=20000,1000-20000" in cmd
    cmd = _seat_cmd(tmp_path, monkeypatch, {})
    assert "--video-bitrate=30000,1000-30000" in cmd
    cmd = _seat_cmd(tmp_path, monkeypatch, {"video_bitrate_kbps": 800})
    assert "--video-bitrate=800,800-800" in cmd
    cmd = _seat_cmd(tmp_path, monkeypatch, {"bitrate_kbps": 12000})   # admin form key
    assert "--video-bitrate=12000,1000-12000" in cmd
    cmd = _seat_cmd(tmp_path, monkeypatch, {"video_bitrate_kbps": "junk"})
    assert "--video-bitrate=30000,1000-30000" in cmd


def test_gnome_seat_always_disables_client_cursor(tmp_path, monkeypatch):
    """The seat portal embeds the cursor in the frames; a client-drawn cursor on
    top doubles/flickers. labwc forwards real cursor metadata, so it keeps it."""
    seat = {"socket": "s", "bus": "b"}
    assert "--enable-cursors=true" in _seat_cmd(tmp_path, monkeypatch, {}, seat)
    assert "--use-browser-cursors=true" in _seat_cmd(tmp_path, monkeypatch, {}, seat)
    assert "--use-browser-cursors=true" not in _seat_cmd(tmp_path, monkeypatch, {})


def test_quality_defaults(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, stream_settings={})
    _stub(monkeypatch)
    cmd, env = engine.build_selkies_cmd(cfg, 1)
    assert env["SELKIES_RATE_CONTROL_MODE"] == "cbr" and "--encoder=h264enc" in cmd
    assert not any(a.startswith("--video-max-qp") for a in cmd)
    assert env["SELKIES_USE_PAINT_OVER_QUALITY"] == "true"
    assert env["SELKIES_VIDEO_PAINTOVER_CRF"] == "12"
    _, env = engine.build_selkies_cmd(
        {**cfg, "stream_settings": {"use_paint_over_quality": False}}, 1)
    assert env["SELKIES_USE_PAINT_OVER_QUALITY"] == "false"



class _Steer:
    """Upstream CongestionSteer cut down to what the cap reads: a queue tick
    measures capacity and backs off to the floor; a clean tick forgets a
    capacity the path delivers past, and raises x1.15."""
    APP_LIMITED = 0.5
    STEP = 1.15

    def __init__(self):
        self.capacity_kbps = None

    def target(self, current, ceiling, floor, goodput_bps, loss, now,
               queue_s=None, offered_bps=None):
        if queue_s:
            self.capacity_kbps = goodput_bps / 1_000
            return floor
        if self.capacity_kbps and goodput_bps / 1_000 * 0.9 > self.capacity_kbps:
            self.capacity_kbps = None
        return min(ceiling, current * 1.15)


def _steer():
    cls = type("S", (_Steer,), {})
    engine.cap_still_raise(cls)
    return cls()


def _tick(s, cur, delivered_kbps, offered_kbps, queue_s=0.0):
    return s.target(cur, 16000, 1000, delivered_kbps * 1000, 0.0, 0, queue_s,
                    None if offered_kbps is None else offered_kbps * 1000)


def test_still_screen_holds_at_measured_capacity():
    s = _steer()
    cur = _tick(s, 16000, 5000, 9000, queue_s=0.5)
    for _ in range(30):
        cur = _tick(s, cur, 200, 200)
    assert cur == 5000


def test_capacity_survives_upstream_forgetting_it():
    """GAME-01 2026-10-24: motion carried just past the measured 1391 kbps,
    upstream dropped the capacity, and the still screen climbed to 16000."""
    s = _steer()
    cur = _tick(s, 16000, 1391, 9000, queue_s=0.8)
    for _ in range(8):
        cur = _tick(s, cur, min(cur, 2000), cur)
    assert s.capacity_kbps is None
    for _ in range(20):
        cur = _tick(s, cur, 200, 200)
    assert cur <= 2000 * 1.15


def test_motion_probes_up_from_a_bogus_low_measurement():
    s = _steer()
    cur = _tick(s, 16000, 553, 9000, queue_s=0.3)
    for _ in range(15):
        cur = _tick(s, cur, cur, cur)       # path keeps up with every raise
    assert cur > 5000


def test_unmeasured_offer_never_raises_past_known():
    s = _steer()
    cur = _tick(s, 16000, 3000, 9000, queue_s=0.3)
    for _ in range(10):
        cur = _tick(s, cur, 0, None)
    assert cur == 3000


def test_no_measurement_yet_is_upstream_behaviour():
    assert _tick(_steer(), 2000, 100, 100) == 2300


def test_stream_override_appends_args(tmp_path):
    f = tmp_path / "stream-override.json"
    argv = ["selkies", "--encoder=h264enc"]
    assert engine.apply_stream_override(argv, f) == argv          # no file: unchanged
    f.write_text('{"args": ["--encoder=av1enc,h265enc,h264enc", "--video-bitrate=30000,1000-30000"]}')
    out = engine.apply_stream_override(argv, f)
    assert out == argv + ["--encoder=av1enc,h265enc,h264enc", "--video-bitrate=30000,1000-30000"]
    f.write_text("not json")
    assert engine.apply_stream_override(argv, f) == argv          # broken file: ignored
    f.write_text('{"args": ["ok", 3]}')
    assert engine.apply_stream_override(argv, f) == argv          # non-string args: ignored


VAINFO_780M = """
      VAProfileH264Main               :	VAEntrypointEncSlice
      VAProfileH264High               :	VAEntrypointEncSlice
      VAProfileHEVCMain               :	VAEntrypointEncSlice
      VAProfileHEVCMain10             :	VAEntrypointEncSlice
      VAProfileAV1Profile0            :	VAEntrypointVLD
      VAProfileAV1Profile0            :	VAEntrypointEncSlice
"""


def test_parse_vainfo_encoders():
    assert engine.parse_vainfo_encoders(VAINFO_780M) == ("av1enc", "h265enc")
    assert engine.parse_vainfo_encoders("VAProfileAV1Profile0 : VAEntrypointVLD") == ()   # decode only
    assert engine.parse_vainfo_encoders("") == ()


def test_encoder_ladder_from_hardware(tmp_path, monkeypatch):
    """A/B 2026-10-30: AV1 at 30 Mbps beat H.264 at 16 (settled text +15-39%).
    Only codecs the GPU encodes lead: selkies would run AV1 in software otherwise."""
    cfg = _cfg(tmp_path, stream_settings={})
    _stub(monkeypatch, hw=("av1enc", "h265enc"))
    cmd, _ = engine.build_selkies_cmd(cfg, 1)
    assert "--encoder=av1enc,h265enc,h264enc" in cmd
    _stub(monkeypatch, hw=())
    cmd, _ = engine.build_selkies_cmd(cfg, 1)
    assert "--encoder=h264enc" in cmd


def test_nvenc_encoders_by_generation():
    assert engine.nvenc_encoders("8.9") == ("av1enc", "h265enc")   # RTX 4090
    assert engine.nvenc_encoders("12.0\n") == ("av1enc", "h265enc")
    assert engine.nvenc_encoders("8.6") == ("h265enc",)            # RTX 30
    assert engine.nvenc_encoders("5.0") == ()
    assert engine.nvenc_encoders("") == ()


# --- transport + TURN -------------------------------------------------------
CF = {"provider": "cloudflare", "token_id": "TID-SECRET", "api_token": "API-SECRET"}
GEN = {"provider": "generic", "host": "turn.example.com", "port": 3478,
       "protocol": "tcp", "tls": True}


def _ss(**kw):
    return {"stream_settings": {"framerate": 60, **kw}}


def test_transport_defaults_to_websockets(tmp_path, monkeypatch):
    _stub(monkeypatch)
    cmd, env = engine.build_selkies_cmd(_cfg(tmp_path), 1)
    assert "--mode=websockets" in cmd
    # no TURN configured: only the demo-relay blanks, never a relay
    assert env["SELKIES_TURN_HOST"] == "" and env["SELKIES_TURN_SHARED_SECRET"] == ""
    assert not any(k.startswith("SELKIES_CLOUDFLARE") for k in env)


def test_webrtc_transport_switches_mode(tmp_path, monkeypatch):
    _stub(monkeypatch)
    cmd, env = engine.build_selkies_cmd(_cfg(tmp_path, **_ss(transport="webrtc")), 1)
    assert "--mode=webrtc" in cmd and "--mode=websockets" not in cmd
    assert "SELKIES_ENABLE_CLOUDFLARE_TURN" not in env


def test_unknown_transport_falls_back(tmp_path, monkeypatch):
    _stub(monkeypatch)
    cmd, _ = engine.build_selkies_cmd(_cfg(tmp_path, **_ss(transport="bogus")), 1)
    assert "--mode=websockets" in cmd


def test_cloudflare_turn_secrets_via_env_only(tmp_path, monkeypatch):
    _stub(monkeypatch)
    cfg = _cfg(tmp_path, **_ss(transport="webrtc", turn=CF))
    cmd, env = engine.build_selkies_cmd(cfg, 1)
    assert env["SELKIES_ENABLE_CLOUDFLARE_TURN"] == "true"
    assert env["SELKIES_CLOUDFLARE_TURN_TOKEN_ID"] == "TID-SECRET"
    assert env["SELKIES_CLOUDFLARE_TURN_API_TOKEN"] == "API-SECRET"
    assert not any("SECRET" in a for a in cmd)


def test_generic_turn_shared_secret(tmp_path, monkeypatch):
    _stub(monkeypatch)
    turn = {**GEN, "shared_secret": "HMAC-SECRET"}
    cmd, env = engine.build_selkies_cmd(_cfg(tmp_path, **_ss(transport="webrtc", turn=turn)), 1)
    assert env["SELKIES_TURN_HOST"] == "turn.example.com"
    assert env["SELKIES_TURN_PORT"] == "3478" and env["SELKIES_TURN_PROTOCOL"] == "tcp"
    assert env["SELKIES_TURN_TLS"] == "true"
    assert env["SELKIES_TURN_SHARED_SECRET"] == "HMAC-SECRET"
    assert "SELKIES_ENABLE_CLOUDFLARE_TURN" not in env
    assert not any("SECRET" in a for a in cmd)


def test_generic_turn_username_password(tmp_path, monkeypatch):
    _stub(monkeypatch)
    turn = {**GEN, "tls": False, "username": "u1", "password": "PW-SECRET"}
    cmd, env = engine.build_selkies_cmd(_cfg(tmp_path, **_ss(transport="webrtc", turn=turn)), 1)
    assert env["SELKIES_TURN_USERNAME"] == "u1" and env["SELKIES_TURN_PASSWORD"] == "PW-SECRET"
    assert env["SELKIES_TURN_TLS"] == "false"
    assert env["SELKIES_TURN_SHARED_SECRET"] == ""     # selkies' built-in default must not win
    assert not any("PW-SECRET" in a for a in cmd)


def test_turn_applied_on_websockets_for_sidebar_webrtc(tmp_path, monkeypatch):
    # The selkies sidebar can switch a viewer to WebRTC on a WebSockets default.
    _stub(monkeypatch)
    cmd, env = engine.build_selkies_cmd(_cfg(tmp_path, **_ss(turn=CF)), 1)
    assert "--mode=websockets" in cmd
    assert env["SELKIES_CLOUDFLARE_TURN_API_TOKEN"] == CF["api_token"]
    assert env["SELKIES_TURN_HOST"] == ""             # demo relay still blanked


def test_turn_env_never_falls_back_to_public_demo_relay():
    for turn in (None, {}, {"provider": "cloudflare", "token_id": "i", "api_token": "t"}):
        env = engine.turn_env(turn)
        assert env["SELKIES_TURN_HOST"] == "" and env["SELKIES_TURN_SHARED_SECRET"] == ""


def test_encoder_order_follows_portal_setting():
    hw = ("av1enc", "h265enc")
    assert engine.encoder_order("auto", hw) == ["av1enc", "h265enc", "h264enc"]
    assert engine.encoder_order(None, hw) == ["av1enc", "h265enc", "h264enc"]
    assert engine.encoder_order("hevc", hw) == ["h265enc", "av1enc", "h264enc"]
    assert engine.encoder_order("H264", hw) == ["h264enc", "av1enc", "h265enc"]
    assert engine.encoder_order("av1", ("h265enc",)) == ["h265enc", "h264enc"]  # no HW AV1: ignored


def test_cmd_uses_portal_encoder(tmp_path, monkeypatch):
    _stub(monkeypatch, dri="/dev/dri/renderD128", hw=("av1enc", "h265enc"))
    cfg = _cfg(tmp_path)
    cfg["stream_settings"] = {"encoder": "hevc"}
    cmd, _ = engine.build_selkies_cmd(cfg, 9000)
    assert "--encoder=h265enc,av1enc,h264enc" in cmd
