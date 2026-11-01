"""Single resolver for the stream_settings delivered to workstation agents:
per-workstation override (ws.stream_settings) over system default."""
from collections.abc import Mapping
from typing import Any

# old key -> 2.0 key; old keys stay honored (frontend writes them until Phase 1)
_VIDEO_ALIASES = {"h264_crf": "video_crf",
                  "h264_streaming_mode": "video_streaming_mode",
                  "h264_paintover_crf": "video_paintover_crf"}
_SEAT_SHELLS = ("gnome", "labwc")
_SEAT_X11 = ("auto", "off")


def is_v2_agent(agent_version: str | None) -> bool:
    try:
        major, minor = (int(x) for x in (agent_version or "").split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (0, 5)


def supports_webrtc(agent_version: str | None) -> bool:
    try:
        parts = tuple(int(x) for x in (agent_version or "").split(".")[:3])
    except ValueError:
        return False
    return len(parts) == 3 and parts >= (0, 9, 30)


STREAM_SYS_KEYS = (
    "WORKSTATION_IDLE_TIMEOUT_S", "WORKSTATION_IDLE_WARN_LEAD_S",
    "WORKSTATION_IDLE_TIMEOUT_ENABLED", "WORKSTATION_SEAT_WIDTH", "WORKSTATION_SEAT_HEIGHT",
    "WORKSTATION_TRANSPORT", "WEBRTC_TURN_PROVIDER", "WEBRTC_MAX_SESSION_H",
    "CLOUDFLARE_TURN_TOKEN_ID", "CLOUDFLARE_TURN_API_TOKEN", "TURN_HOST", "TURN_PORT",
    "TURN_PROTOCOL", "TURN_TLS",
    "WORKSTATION_DEFAULT_ENCODER", "WORKSTATION_DEFAULT_FRAMERATE", "WORKSTATION_DEFAULT_BITRATE_KBPS",
    "WORKSTATION_DEFAULT_CRF", "WORKSTATION_DEFAULT_PAINT_OVER", "WORKSTATION_DEFAULT_STREAMING_MODE",
    "WORKSTATION_DEFAULT_FULLCOLOR", "TURN_SHARED_SECRET", "TURN_USERNAME", "TURN_PASSWORD",
)


def stream_sys_settings(store) -> dict[str, Any]:
    """Snapshot of the system settings the resolver needs (store = SettingsService)."""
    return {k: store.get(k) for k in STREAM_SYS_KEYS}


def _turn_config(sys: Mapping[str, Any]) -> dict | None:
    """TURN credentials for the agent, or None when the provider is unset/incomplete."""
    provider = sys.get("WEBRTC_TURN_PROVIDER")
    if provider == "cloudflare":
        tid, tok = sys.get("CLOUDFLARE_TURN_TOKEN_ID"), sys.get("CLOUDFLARE_TURN_API_TOKEN")
        if tid and tok:
            return {"provider": "cloudflare", "token_id": tid, "api_token": tok}
    elif provider == "generic" and sys.get("TURN_HOST"):
        turn = {"provider": "generic", "host": sys["TURN_HOST"],
                "port": sys.get("TURN_PORT"), "protocol": sys.get("TURN_PROTOCOL"),
                "tls": bool(sys.get("TURN_TLS"))}
        if sys.get("TURN_SHARED_SECRET"):
            return {**turn, "shared_secret": sys["TURN_SHARED_SECRET"]}
        if sys.get("TURN_USERNAME") and sys.get("TURN_PASSWORD"):
            return {**turn, "username": sys["TURN_USERNAME"], "password": sys["TURN_PASSWORD"]}
    return None


# (system key, stream key(s) that count as already set, output key, built-in value)
_DEFAULTS = (
    ("WORKSTATION_DEFAULT_ENCODER", ("encoder",), "encoder", "auto"),
    ("WORKSTATION_DEFAULT_FRAMERATE", ("framerate",), "framerate", 60),
    ("WORKSTATION_DEFAULT_BITRATE_KBPS", ("bitrate_kbps",), "bitrate_kbps", 0),
    ("WORKSTATION_DEFAULT_CRF", ("h264_crf", "video_crf"), "video_crf", 25),
    ("WORKSTATION_DEFAULT_PAINT_OVER", ("use_paint_over_quality",), "use_paint_over_quality", True),
    ("WORKSTATION_DEFAULT_STREAMING_MODE", ("h264_streaming_mode", "video_streaming_mode"),
     "video_streaming_mode", False),
    ("WORKSTATION_DEFAULT_FULLCOLOR", ("video_fullcolor",), "video_fullcolor", False),
)


def _apply_defaults(eff: dict, sys: Mapping[str, Any]) -> None:
    """System-wide stream defaults: only when the workstation has no value and the
    default differs from the built-in (so unset/default output is unchanged)."""
    for skey, have, out, builtin in _DEFAULTS:
        v = sys.get(skey)
        if v is None or v == builtin or any(h in eff for h in have):
            continue
        eff[out] = v


def resolve_stream_settings(ws_ss: dict | None, sys: Mapping[str, Any],
                            agent_version: str | None) -> dict:
    ss = dict(ws_ss or {})
    eff = {**ss,
           "idle_timeout_s": ss.get("idle_timeout_s", sys.get("WORKSTATION_IDLE_TIMEOUT_S")),
           "idle_warn_lead_s": ss.get("idle_warn_lead_s", sys.get("WORKSTATION_IDLE_WARN_LEAD_S")),
           "idle_timeout_enabled": ss.get("idle_timeout_enabled",
                                          sys.get("WORKSTATION_IDLE_TIMEOUT_ENABLED"))}
    if not is_v2_agent(agent_version):
        return eff
    if supports_webrtc(agent_version):
        want = ss.get("transport")
        transport = want if want in ("websockets", "webrtc") else \
            sys.get("WORKSTATION_TRANSPORT") or "websockets"
        if sys.get("TURN_OVER_BUDGET"):
            transport = "websockets"            # cost control: TURN budget reached
            eff["turn_budget_paused"] = True    # gateway refuses sidebar WebRTC too
        eff["transport"] = transport
        eff["max_session_s"] = int(sys.get("WEBRTC_MAX_SESSION_H") or 0) * 3600
        # Any transport: the transport is the default, a viewer's sidebar may pick WebRTC.
        turn = None if eff.get("turn_budget_paused") else _turn_config(sys)
        if turn:
            eff["turn"] = turn
    _apply_defaults(eff, sys)
    for old, new in _VIDEO_ALIASES.items():
        if new not in eff and old in eff:
            eff[new] = eff[old]
    shell = ss.get("seat_shell")
    eff["seat_shell"] = shell if shell in _SEAT_SHELLS else "gnome"
    eff["seat_x11"] = ss["seat_x11"] if ss.get("seat_x11") in _SEAT_X11 else "auto"
    eff["seat_width"] = ss.get("seat_width", sys.get("WORKSTATION_SEAT_WIDTH"))
    eff["seat_height"] = ss.get("seat_height", sys.get("WORKSTATION_SEAT_HEIGHT"))
    return eff
