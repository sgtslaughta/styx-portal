"""Shallow pipe: keep the controlling tab's video queue near the path floor
(docs/superpowers/specs/2026-10-30-shallow-pipe-design.md).

Runtime patches of selkies 2.1, installed by engine.seat_selkies_main. The
selkies module is passed in rather than imported, so tests run without it.
"""
import logging

log = logging.getLogger("ws")


def queue_ms(state: dict, wm) -> float | None:
    """The queue standing on the path this tick: the least round trip among
    the acks since the last tick, less its own serialization, over the floor.
    The same reading selkies' `_steer_bitrate_to_link` makes, as a number
    rather than a verdict. Call before it: it advances `link_tick_at`."""
    floor = state.get("rtt_floor_ms") or 0.0
    acks = state.get("link_acks") or ()
    last = state.get("link_tick_at", 0.0)
    fresh = sum(1 for a in acks if a[0] > last)
    if not floor or not fresh:
        return None
    queued = wm._queued_round_trips(acks, wm._path_rate(acks, floor))
    # Upstream's `stand`: a thin window is judged with the acks before it.
    stand = queued[-max(fresh, 2 * getattr(wm, "LINK_RISE_ACKS", 4)):]
    return max(0.0, min(stand) - floor)


def trace_steer(server_cls, wm, steer_cls) -> None:
    """Hand each congestion tick's queue to the display's steer (`styx_q_ms`)
    and log one STYX-CC line per measured tick, for cc_report.py.
    ponytail: the trace is for the Phase 1 A/B; drop or gate behind a setting once tuned."""
    orig = server_cls._steer_bitrate_to_link

    def steer(self, display_id, state, now):
        q = queue_ms(state, wm)
        if q is not None:
            state.setdefault("link_steer", steer_cls()).styx_q_ms = q
        out = orig(self, display_id, state, now)
        if q is not None:
            log.info(f"STYX-CC {display_id} q={q:.0f} floor={state.get('rtt_floor_ms', 0):.0f} "
                     f"dlv={state.get('link_delivered_bps', 0) / 1000:.0f} "
                     f"rate={state.get('link_kbps', 0):.0f}")
        return out

    server_cls._steer_bitrate_to_link = steer
