"""Single resolver for the stream_settings delivered to workstation agents:
per-workstation override (ws.stream_settings) over system default."""
from collections.abc import Mapping
from typing import Any

# old key -> 2.0 key; old keys stay honored (frontend writes them until Phase 1)
_VIDEO_ALIASES = {"h264_crf": "video_crf",
                  "h264_streaming_mode": "video_streaming_mode",
                  "h264_paintover_crf": "video_paintover_crf"}
_SEAT_SHELLS = ("gnome", "labwc")


def is_v2_agent(agent_version: str | None) -> bool:
    try:
        major, minor = (int(x) for x in (agent_version or "").split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (0, 5)


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
    for old, new in _VIDEO_ALIASES.items():
        if new not in eff and old in eff:
            eff[new] = eff[old]
    shell = ss.get("seat_shell")
    eff["seat_shell"] = shell if shell in _SEAT_SHELLS else "gnome"
    eff["seat_width"] = ss.get("seat_width", sys.get("WORKSTATION_SEAT_WIDTH"))
    eff["seat_height"] = ss.get("seat_height", sys.get("WORKSTATION_SEAT_HEIGHT"))
    eff["cursor_workaround"] = ss.get("cursor_workaround",
                                      sys.get("WORKSTATION_CURSOR_WORKAROUND"))
    return eff
