"""Engine logic for the pixelflux/selkies 2.x agent — pure functions only.

mirror: attach to a live X display (XShm capture), resolution locked to the
        physical screen so selkies never xrandr-resizes the user's monitor.
seat:   pixelflux's own Wayland compositor; host apps join via WAYLAND_DISPLAY.
"""
import base64
import glob
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import bundle_patch
import shallow_pipe

HOME = Path.home()
DRI_DIR = "/dev/dri"
SEAT_SINK = "styx-seat"    # null sink so seat audio never hits the speakers


def _find_xauthority(cfg: dict) -> str | None:
    """systemd --user starts with an empty env; resolve the cookie explicitly.
    Location varies by distro/display manager."""
    uid = os.getuid()
    candidates = [
        cfg.get("xauthority"),
        os.environ.get("XAUTHORITY"),
        str(HOME / ".Xauthority"),
        f"/run/user/{uid}/.mutter-Xwaylandauth",      # GNOME Xwayland
        f"/run/user/{uid}/gdm/Xauthority",            # GDM
    ]
    candidates += [str(p) for p in sorted(HOME.glob(".vnc/*Xauthority"))]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def pick_free_port() -> int:
    """A free loopback port for the selkies<->gateway link (race window
    between close and child bind is acceptable on loopback)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pick_dri_node() -> str:
    nodes = sorted(glob.glob(os.path.join(DRI_DIR, "renderD*")))
    return nodes[0] if nodes else ""


# VA-API encode profiles -> selkies encoders, most efficient first.
VA_ENCODERS = (("VAProfileAV1", "av1enc"), ("VAProfileHEVC", "h265enc"))


def parse_vainfo_encoders(text: str) -> tuple:
    """The selkies encoders past H.264 that `vainfo` shows the GPU encoding."""
    enc = [line.split(":")[0].strip() for line in text.splitlines() if "VAEntrypointEnc" in line]
    return tuple(name for prefix, name in VA_ENCODERS if any(p.startswith(prefix) for p in enc))


def nvenc_encoders(compute_cap: str) -> tuple:
    """NVENC encoders past H.264 for an `nvidia-smi` compute capability:
    AV1 from Ada (8.9, RTX 40), HEVC from Maxwell 2 (5.2)."""
    try:
        cc = tuple(int(x) for x in compute_cap.strip().split("."))
    except ValueError:
        return ()
    return ("av1enc", "h265enc") if cc >= (8, 9) else ("h265enc",) if cc >= (5, 2) else ()


def _probe_nvenc() -> tuple:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    return nvenc_encoders(out.splitlines()[0]) if out.strip() else ()


_HW_ENCODERS: dict = {}


_CODEC_ENCODER = {"av1": "av1enc", "hevc": "h265enc", "h264": "h264enc"}


def encoder_order(pref, hw: tuple) -> list:
    """Portal `encoder` (auto|av1|hevc|h264) moves that codec to the front of
    the hardware list; the rest stay as fallbacks for browsers that cannot
    decode it. A codec the GPU lacks is ignored: selkies would encode it in
    software. auto/unknown keeps the default most-efficient-first order."""
    order = [*hw, "h264enc"]
    want = _CODEC_ENCODER.get(str(pref or "").lower())
    if want in order:
        order.remove(want)
        order.insert(0, want)
    return order


def hw_encoders(node: str) -> tuple:
    """Hardware AV1/HEVC encoders on `node`, probed once. selkies falls back to
    a software encoder (SVT-AV1, x265) for a codec the GPU lacks, which would
    pin the CPU, so only probed codecs go ahead of H.264. No node or no vainfo:
    none, and the session stays on H.264. NVIDIA (no VA-API encode): NVENC by GPU
    generation. ponytail: first GPU only; multi-GPU hosts pick by node later."""
    if not node:
        return ()
    if node not in _HW_ENCODERS:
        try:
            out = subprocess.run(["vainfo", "--display", "drm", "--device", node],
                                 capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        _HW_ENCODERS[node] = parse_vainfo_encoders(out) or _probe_nvenc()
    return _HW_ENCODERS[node]


def query_display_geometry(display: str, xauthority: str | None) -> tuple[int, int]:
    """Screen size of a live X display, via the venv's python-xlib.

    Xlib reads XAUTHORITY from the process env at connect time; set it only
    for the duration of the query so the supervisor's env stays clean.
    """
    from Xlib import display as xdisplay  # venv dep of selkies
    saved = os.environ.get("XAUTHORITY")
    if xauthority:
        os.environ["XAUTHORITY"] = xauthority
    try:
        d = xdisplay.Display(display)
        try:
            s = d.screen()
            return s.width_in_pixels, s.height_in_pixels
        finally:
            d.close()
    finally:
        if xauthority:
            if saved is None:
                os.environ.pop("XAUTHORITY", None)
            else:
                os.environ["XAUTHORITY"] = saved


def resolve_monitor_source() -> str:
    """Monitor source of the default sink ('' = no audio server -> disable).
    selkies' baked-in default 'output.monitor' only exists in containers."""
    try:
        import pulsectl
        with pulsectl.Pulse("styx-agent") as p:
            return p.server_info().default_sink_name + ".monitor"
    except Exception:
        return ""


def ensure_seat_sink() -> str:
    """Create (idempotently) a null sink for seat audio; returns its monitor."""
    import pulsectl
    with pulsectl.Pulse("styx-agent") as p:
        if not any(s.name == SEAT_SINK for s in p.sink_list()):
            p.module_load("module-null-sink",
                          f"sink_name={SEAT_SINK} "
                          f"sink_properties=device.description={SEAT_SINK}")
    return f"{SEAT_SINK}.monitor"


MIC_SOURCE = "SelkiesVirtualMic"   # name selkies expects to find


def _int_in(value, lo: int, hi: int) -> int | None:
    """Portal-supplied setting -> int within [lo, hi], else None (ignore)."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def ensure_mic_source() -> str:
    """Pre-create the virtual microphone plumbing selkies expects.

    selkies plays browser mic audio into a sink literally named 'input' and
    needs a source 'SelkiesVirtualMic' on its monitor. It tries to create
    the source via module-virtual-source, which PipeWire's pulse shim
    accepts but never materializes — so build the equivalent here with
    modules PipeWire does implement (null-sink + remap-source). selkies
    then finds the existing source and proceeds."""
    import pulsectl
    with pulsectl.Pulse("styx-agent") as p:
        if not any(s.name == "input" for s in p.sink_list()):
            p.module_load("module-null-sink",
                          "sink_name=input "
                          "sink_properties=device.description=styx-mic-in")
        if not any(s.name == MIC_SOURCE for s in p.source_list()):
            p.module_load("module-remap-source",
                          f"master=input.monitor source_name={MIC_SOURCE} "
                          f"source_properties=device.description={MIC_SOURCE}")
    return MIC_SOURCE


def guard_default_socket(runtime_dir: str):
    """Hold the wayland-0 slot so neither seat compositor can bind it.

    wl_display_connect(NULL) falls back to literally "wayland-0" when
    WAYLAND_DISPLAY is unset — true for every GTK/Qt app in an X11 login
    session. If the seat compositor or labwc grabs wayland-0, those host
    apps silently render INTO the seat (live-seen: Ubuntu's DING desktop
    icons floating over the seat desktop). Mirror libwayland's locking
    (flock on wayland-0.lock) so wl_display_add_socket_auto skips slot 0.

    Returns the held lock file (keep referenced for the agent's lifetime),
    or None when a real Wayland session already owns the slot."""
    import fcntl
    lock_path = Path(runtime_dir) / "wayland-0.lock"
    try:
        f = open(lock_path, "a+")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    # We own the slot: drop any stale socket file so fallback connects
    # fail fast and clients move on to X11.
    (Path(runtime_dir) / "wayland-0").unlink(missing_ok=True)
    return f


def wait_for_wayland_socket(runtime_dir: str, before: set[str],
                            since_ts: float, timeout: float = 15,
                            exclude: set[str] | None = None) -> str | None:
    """The compositor picks the first free wayland-N. A socket counts if its
    name is new OR its file was (re)created after `since_ts` — stale socket
    files survive process death, so a pure before/after name diff misses a
    compositor that rebinds the same wayland-N (seen on agent restart).

    `exclude` skips known sockets (e.g. the seat compositor's own socket when
    hunting for the nested shell's socket) — without it, the just-created seat
    socket matches the `since_ts` mtime slack and is returned by mistake."""
    exclude = exclude or set()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for p in sorted(Path(runtime_dir).glob("wayland-*")):
            if p.name.endswith(".lock") or p.name in exclude:
                continue
            if p.name not in before:
                return p.name
            try:
                if p.stat().st_mtime >= since_ts:
                    return p.name
            except FileNotFoundError:
                continue
        time.sleep(0.2)
    return None



CLIP_SOCKET = "styx-clipboard.sock"


def clip_socket_path() -> str:
    rd = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(rd, CLIP_SOCKET)


def _clip_open(req: dict, path: str) -> socket.socket:
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(5)
    s.connect(path)
    s.sendall(json.dumps(req).encode() + b"\n")
    s.shutdown(socket.SHUT_WR)
    return s


def clip_call(req: dict, path: str | None = None) -> bytes:
    """One request to seat_clipboard.py; raises on an error reply."""
    with _clip_open(req, path or clip_socket_path()) as s:
        out = b"".join(iter(lambda: s.recv(65536), b""))
    if out[:1] != b"+":
        raise RuntimeError(out[1:].decode(errors="replace") or "seat clipboard: no reply")
    return out[1:]


def clip_watch(on_change, path: str | None = None) -> None:
    """Daemon thread calling on_change(mimes) per seat selection change;
    reconnects when seat_portal restarts (refit, self-heal)."""
    import threading

    def run():
        while True:
            try:
                with _clip_open({"op": "watch"}, path or clip_socket_path()) as s:
                    s.settimeout(None)
                    f = s.makefile("rb")
                    if f.read(1) != b"+":
                        raise OSError("watch refused")
                    for line in f:
                        on_change(json.loads(line))
            except (OSError, ValueError):
                pass
            time.sleep(1)
    threading.Thread(target=run, daemon=True, name="styx-clip-watch").start()


SEAT_CLIPBOARD = {
    "clipboard_types_app": lambda _d: json.loads(clip_call({"op": "types"})),
    "clipboard_read_app": lambda _d, mime: clip_call({"op": "read", "mime": mime}),
    "clipboard_write_app": lambda _d, offered: clip_call({"op": "write", "offers": [
        [m, base64.b64encode(bytes(d)).decode()] for m, d in offered]}),
    "clipboard_watch_app": lambda _d, cb: clip_watch(cb),
}


STREAM_OVERRIDE = HOME / ".local/share/styx-agent/stream-override.json"


def apply_stream_override(argv: list, path: Path = STREAM_OVERRIDE) -> list:
    """argv plus the selkies flags in `path` ({"args": [...]}), which win as
    argparse keeps the last value. The stream A/B harness swaps encoder and
    bitrate this way and restarts only selkies, so the seat survives.
    ponytail: dev/harness hook; production settings still come from the portal."""
    try:
        extra = json.loads(path.read_text()).get("args", [])
    except (OSError, ValueError, AttributeError):
        return argv
    if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
        return argv
    return argv + extra


def seat_selkies_main() -> None:
    """selkies for the GNOME seat (`python engine.py <selkies args>`). Mutter
    has no wlr/ext data-control, so selkies' clipboard calls aimed at the seat
    socket fail; route them to seat_clipboard.py, which serves the seat's
    clipboard (all flavours) from Mutter's RemoteDesktop clipboard API."""
    sys.argv = apply_stream_override(sys.argv)     # before selkies parses its settings on import
    from pixelflux import ScreenCapture
    from selkies import input_handler
    from selkies.__main__ import main

    class SeatCapture:
        def __init__(self):
            self._real = ScreenCapture()

        def __getattr__(self, name):
            return SEAT_CLIPBOARD.get(name) or getattr(self._real, name)

    input_handler.ScreenCapture = SeatCapture
    from selkies import websockets_mode
    from selkies.stream_server import CongestionSteer
    cap_still_raise(CongestionSteer)
    shallow_pipe.trace_steer(websockets_mode.DataStreamingServer, websockets_mode, CongestionSteer)
    import selkies
    shallow_pipe.owner_gate(websockets_mode._VideoRelay, websockets_mode, selkies.__version__)
    sys.exit(main())


def cap_still_raise(steer_cls) -> None:
    """selkies 2.1 raises the CBR target x1.15/s on every clean tick, a still
    screen's trickle included, and forgets the path capacity it measured as
    soon as motion delivers a little past it. After a backoff the target so
    climbs back to the ceiling without testing the path, and the next motion
    bursts into a queue: the "poor connection" sawtooth on a slow path.

    Keep our own `styx_known_kbps`: the last capacity selkies measured, raised
    by what motion actually delivers, never forgotten. A still or unmeasured
    tick never raises past it; a motion tick raises at most STEP past it, so
    a faster path still unlocks within seconds of real motion.
    ponytail: drop once upstream fixes selkies-project/selkies#489."""
    orig = steer_cls.target

    def target(self, current, ceiling, floor, goodput_bps, loss, now,
               queue_s=None, offered_bps=None):
        before = self.capacity_kbps
        out = orig(self, current, ceiling, floor, goodput_bps, loss, now,
                   queue_s, offered_bps)
        known = getattr(self, "styx_known_kbps", None)
        if self.capacity_kbps is not None and self.capacity_kbps != before:
            known = self.capacity_kbps           # fresh measurement wins
        moving = (offered_bps is not None
                  and offered_bps >= current * 1_000 * self.APP_LIMITED)
        if known is not None and not queue_s and moving:
            known = max(known, goodput_bps / 1_000)
        self.styx_known_kbps = known
        if known is None or queue_s or out <= current:
            return out
        return max(current, min(out, known * (self.STEP if moving else 1.0)))

    steer_cls.target = target


def turn_env(turn) -> dict:
    """TURN settings -> SELKIES_* env (secrets never touch argv, so not `ps`).
    selkies defaults to a public demo relay (openrelay + its published shared
    secret): always blank host + secret so only a relay the admin configured
    is ever used; no TURN configured = direct/STUN only."""
    off = {"SELKIES_TURN_HOST": "", "SELKIES_TURN_SHARED_SECRET": ""}
    if not isinstance(turn, dict):
        return off
    if turn.get("provider") == "cloudflare":
        return {**off, "SELKIES_ENABLE_CLOUDFLARE_TURN": "true",
                "SELKIES_CLOUDFLARE_TURN_TOKEN_ID": str(turn.get("token_id", "")),
                "SELKIES_CLOUDFLARE_TURN_API_TOKEN": str(turn.get("api_token", ""))}
    if turn.get("provider") != "generic":
        return off
    env = {"SELKIES_TURN_HOST": str(turn.get("host", "")),
           "SELKIES_TURN_PORT": str(turn.get("port", 3478)),
           "SELKIES_TURN_PROTOCOL": "tcp" if turn.get("protocol") == "tcp" else "udp",
           "SELKIES_TURN_TLS": "true" if turn.get("tls") else "false",
           # selkies ships a public demo secret as default: blank it unless ours
           "SELKIES_TURN_SHARED_SECRET": str(turn.get("shared_secret", ""))}
    if not env["SELKIES_TURN_SHARED_SECRET"]:
        env["SELKIES_TURN_USERNAME"] = str(turn.get("username", ""))
        env["SELKIES_TURN_PASSWORD"] = str(turn.get("password", ""))
    return env


def build_selkies_cmd(cfg: dict, internal_port: int,
                      seat: dict | None = None) -> tuple[list[str], dict]:
    """argv + env for selkies 2.x. Secrets travel via env, never argv.

    seat: {"socket", "bus"} of a headless GNOME seat (host capture via the
    portal), or None for the labwc seat (pixelflux's own compositor) / mirror.
    Mirror mode queries the live X display and may raise; the supervisor reports it.
    """
    install = Path(cfg["install_dir"])
    bundle_patch.apply(install, lambda m: print(m, flush=True))  # before the page is served
    s = cfg.get("stream_settings", {})
    transport = "webrtc" if s.get("transport") == "webrtc" else "websockets"
    env = {
        "HOME": str(HOME),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
        "PYTHONNOUSERSITE": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "FILE_MANAGER_PATH": os.environ.get("FILE_MANAGER_PATH", str(HOME / "Downloads")),
    }
    cmd = [
        str(install / "venv/bin/selkies"),
        f"--port={internal_port}",          # 2.0 binds loopback by default
        "--enable-basic-auth=false",        # gateway owns auth
        f"--mode={transport}",
        f"--framerate={s.get('framerate', 60)}",
        "--second-screen=false",
        # Off until their phase ships (spec §6): devices, printing.
        "--printing-enabled=false|locked", "--microphone-enabled=false|locked",
        "--webcam-enabled=false|locked", "--gamepad-enabled=false|locked",
        # 10-bit H.264 exists only on x264: on our GPUs it would mean CPU encode.
        "--video-10bit=false|locked",
    ]
    dri = pick_dri_node()
    # AV1 -> HEVC -> H.264 unless the portal picks a codec: the first the
    # browser decodes wins (selkies steps down).
    cmd.insert(4, "--encoder=" + ",".join(
        encoder_order(s.get("encoder"), hw_encoders(dri))))
    if dri:
        cmd += [f"--encode-dri={dri}", f"--render-dri={dri}"]
        # Client pushes use_cpu=true; "|locked" keeps the GPU encoder on.
        env["SELKIES_USE_CPU"] = "false|locked"

    if seat is not None:                     # headless GNOME seat
        cmd[0:1] = [str(install / "venv/bin/python"), str(install / "engine.py")]
        cmd += ["--wayland=true", f"--wayland-host-display={seat['socket']}"]
        # The seat portal sends the cursor as metadata; the browser draws it
        # locally so pointer motion never waits on a video round trip.
        cmd += ["--enable-cursors=true", "--use-browser-cursors=true"]
        env.update({"DBUS_SESSION_BUS_ADDRESS": seat["bus"],
                    "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
                    "XDG_SESSION_TYPE": "wayland"})
        monitor = f"{SEAT_SINK}.monitor"
    elif cfg.get("mode") == "seat":          # labwc seat (fallback)
        cmd += ["--wayland=true",
                f"--wayland-socket-index={cfg.get('seat_socket_index', 1)}"]
        monitor = resolve_monitor_source()
    else:                                    # mirror
        env["DISPLAY"] = cfg["display"]
        xauth = _find_xauthority(cfg)
        if xauth:
            env["XAUTHORITY"] = xauth
        w, h = query_display_geometry(cfg["display"], xauth)
        cmd += [f"--manual-width={w}", f"--manual-height={h}"]
        monitor = resolve_monitor_source()

    # Quality knobs: 2.0 names, old h264_* keys still honored (spec §4).
    crf = _int_in(s.get("video_crf", s.get("h264_crf")), 5, 50)
    if crf is not None:
        env["SELKIES_VIDEO_CRF"] = str(crf)
    streaming = s.get("video_streaming_mode", s.get("h264_streaming_mode"))
    # 2.0 defaults streaming mode ON; keep today's default (off) unless asked.
    env["SELKIES_VIDEO_STREAMING_MODE"] = "true" if streaming is True else "false"
    # Admin bitrate is the default AND the ceiling; viewers may lower it. Floor
    # 1000 kbps: stale 1.x storage sends 8 (Mbps) which would otherwise mean 8 kbps.
    kbps = _int_in(s.get("video_bitrate_kbps", s.get("bitrate_kbps")), 500, 200000) or 30000
    lo = min(1000, kbps)
    cmd.append(f"--video-bitrate={kbps},{lo}-{kbps}")
    # CBR at the admin bitrate: CRF + a QP cap made scrolls burst far past the
    # bitrate and stutter through the tunnel. Paint-over (CRF below) re-sharpens
    # text once the screen settles.
    env["SELKIES_RATE_CONTROL_MODE"] = "cbr"
    env["SELKIES_USE_PAINT_OVER_QUALITY"] = (
        "false" if s.get("use_paint_over_quality") is False else "true")
    # 4:4:4 chroma is opt-in: crisp text, but no AMD/Intel VA-API driver
    # encodes H.264 4:4:4, so selkies drops to software x264 (bigger frames,
    # CPU) — on the EliteMini that starved audio. Initial value only; the
    # panel can still switch it per browser.
    env["SELKIES_VIDEO_FULLCOLOR"] = (
        "true" if s.get("video_fullcolor") is True else "false")
    pcrf = _int_in(s.get("video_paintover_crf", s.get("h264_paintover_crf")), 5, 50)
    env["SELKIES_VIDEO_PAINTOVER_CRF"] = str(12 if pcrf is None else pcrf)

    if transport == "webrtc":
        env.update(turn_env(s.get("turn")))
    if monitor:
        env["SELKIES_AUDIO_ENABLED"] = "true"
        cmd.append(f"--audio-device-name={monitor}")
    else:
        env["SELKIES_AUDIO_ENABLED"] = "false"
    return cmd, env


if __name__ == "__main__":
    seat_selkies_main()
