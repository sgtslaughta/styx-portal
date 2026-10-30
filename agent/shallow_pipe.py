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


OWNER_LAG_S = 0.1      # queue past the round trip the controlling tab may build
GATED_SELKIES = "2.1.0"


def owner_gate(relay_cls, wm, version: str) -> None:
    """The shallow-pipe gate for the tab that owns the display. Upstream
    gates only other pages (`_room`); the owner's frames queue up to the 2 s
    relay budget, so a Wi-Fi hiccup becomes seconds of late video. Past
    OWNER_LAG_S of queue a delta is left out the way a page's is: the encoder
    predicts past it (`_lose` -> `_repair`). Anchors and frame_num-wrap frames
    always go.
    ponytail: copy of upstream _forward (selkies 2.1.0); drop when selkies
    gates the owner (issue TBD). Another version keeps upstream's."""
    if version != GATED_SELKIES:
        log.warning(f"shallow pipe: selkies {version} != {GATED_SELKIES}; owner gate off")
        return

    def _forward(self, frame_id, reference, anchor=False):
        kept = self.numbered and not self.since_key % wm.FRAME_NUM_WRAP
        if reference not in self.sent:
            self._lose(frame_id)
            return self._repair()
        if self.lost_first is not None:
            if not anchor or kept or self._anchor_room():
                self._end_lost()
                return True
            self.lost_first = frame_id
            self.lost_told = False
            self._lose(frame_id)
            return self._repair()
        if self.server._owns_display(self.ws, self.display_id):
            self.gauged = True      # pings go behind the owner's frames too, so _lag() reads
            if kept or anchor or self._lag() < OWNER_LAG_S:
                return True
            self._lose(frame_id)
            return self._repair()
        self.gauged = True
        if anchor and self._anchor_room():
            return True
        if not kept and not self._room():
            self._lose(frame_id)
            return self._repair()
        return True

    relay_cls._forward = _forward


CALM_MS = 30.0         # queue under this: hold or probe
COLLAPSE_MS = 150.0    # queue past this: the path fell away (a hotspot dip)
EASE_MS = 300.0        # between: target = delivered * (1 - q / EASE_MS)
PROBE = 1.05           # per second near known capacity, and past it at most
RECOVER = 1.15         # per second while under RECOVER_SHARE of known capacity
RECOVER_SHARE = 0.85
SETTLE_S = 0.5         # past a collapse's drain before the queue is read again
COLLAPSE_CUT = 0.5


def smooth_steer(steer_cls) -> None:
    """Replace selkies' CBR steer (cut to ~half once a queue reads, then climb
    x1.15/s back into it) with one proportional to the queue it reads
    (`styx_q_ms`, from trace_steer): ease off in step with the queue, cut hard
    only on a collapse and then hold while it drains, and probe slowly, never
    past what a calm path has delivered. A still screen's trickle holds the
    rate and teaches nothing. A queue teaches the path's capacity (what it
    delivered meanwhile); under most of it the rate climbs back fast.
    Same signature as CongestionSteer.target.
    ponytail: replaces selkies' halving steer; drop once upstream adopts
    delay-proportional backoff (issue TBD; also closes selkies#489)."""
    def target(self, current, ceiling, floor, goodput_bps, loss, now,
               queue_s=None, offered_bps=None):
        last, self._tick_at = getattr(self, "_tick_at", None), now
        dt = 1.0 if last is None else min(max(now - last, 0.0), 2.0)

        def clamp(x):
            return max(floor, min(ceiling, x))

        q = getattr(self, "styx_q_ms", None)
        d = goodput_bps / 1_000
        moving = offered_bps is None or offered_bps >= current * 1_000 * getattr(self, "APP_LIMITED", 0.5)
        if q is None or not moving or now < getattr(self, "styx_hold_until", 0.0):
            return clamp(current)
        if q >= CALM_MS and d > 0:
            self.styx_known_kbps = d
        if q >= COLLAPSE_MS:
            # The cut drains the queue in ~2q; a tick inside that still reads it.
            self.styx_hold_until = now + 2 * q / 1_000 + SETTLE_S
            return clamp(min(current, d * COLLAPSE_CUT) if d > 0 else current * COLLAPSE_CUT)
        if q >= CALM_MS:
            return clamp(min(current, d * (1 - q / EASE_MS)))
        known = self.styx_known_kbps = max(getattr(self, "styx_known_kbps", None) or 0.0, d)
        step = RECOVER if known and current < known * RECOVER_SHARE else PROBE
        raised = current * step ** dt
        return clamp(min(raised, known * PROBE) if known else raised)

    steer_cls.target = target
