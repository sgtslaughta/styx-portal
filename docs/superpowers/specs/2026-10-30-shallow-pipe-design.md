# Shallow Pipe — Phase 1 of the stream smoothness push

Date: 2026-10-30 · Branch: from `feat/selkies-2.1` · Status: design

## Why

Goal (user's words): "crisp text with no stutter when scrolling, reliable, sharp,
fast/responsive". Benchmark: Parsec ("feels instant and text is sharp").
Constraint (user): video stays on the WebSocket through the Cloudflare tunnel.
No UDP/WebRTC. Links: home Wi-Fi, office Wi-Fi, sometimes a phone hotspot.

Measured root cause (selkies.log on the mini, 784 congestion events, 2026-10-30):

1. **Deep queue on the controlling tab.** In selkies 2.1 the owner's relay is
   bounded only by `VIDEO_RELAY_BUDGET_SECONDS=2.0` / 4 MiB
   (`websockets_mode.py:225-226,3270`). The shallow-pipe gate (`_room()`/`_lag()`,
   `ROOM_FRAMES=3`, `LAG=0.1s`, `websockets_mode.py:1236-1270`) is skipped for the
   owner (`_forward` returns True, `websockets_mode.py:1302-1303`).
2. **Late, hard congestion response (sawtooth).** `_steer_bitrate_to_link`
   (`websockets_mode.py:3806`) runs every 0.5 s and only reads a queue once RTT is
   past floor + 40 ms + jitter/2 over a window. At each cut the RTT is
   already 3.4× floor (median), 7.8× (p90). The cut lands at ~51% of the prior
   rate (`CongestionSteer.target`, `stream_server.py:285-425`), then
   climbs ×1.15/s back. Result: lag spike → blur → repeat.
3. Backpressure gate twitches at 1–3 frames of desync (291 triggers in the last
   3k log lines). Each trigger drops a frame. Recovery uses reference
   invalidation (`invalidate_reference`), which is cheap and should be kept.

Note: the log spans agent versions, and our `cap_still_raise` patch
(`agent/engine.py:264`) already damps part of (2). A fresh baseline on 0.9.10 is
step one (see Measurement).

## Goals

- In-flight video on the controlling tab stays near the path floor: target
  ≤ ~100 ms queued beyond floor RTT.
- No sawtooth. Bitrate tracks measured delivery smoothly. It eases off on the
  first sign of RTT growth and probes up gently.
- On a link hiccup, skip delta frames *before* they enter TCP (reuse the existing
  reference-invalidation recovery) instead of queueing seconds of video.

## Success measure (vs fresh 0.9.10 baseline, same scripted session)

| Metric | Source | Target |
|---|---|---|
| RTT / floor during scroll, p50 / p90 | ack RTT log | < 1.5× / < 2.5× |
| Bitrate cuts > 30% per 5 min | congestion log | near 0 |
| Delivered kbps variance on steady link | ack window | lower than baseline |
| Frames skipped ("lost by a client") per 5 min | ws log | ≤ baseline (skips must be rare, not a new stutter source) |
| Subjective: scroll a long page / type in terminal on hotspot | user | "feels smooth" |

## Non-goals

- UDP/WebRTC transport. AV1. 4:4:4 tuning. Encoder (pixelflux/Rust) changes: those are Phase 2
  (damage regions → per-region quality, VAAPI ROI).
- Rewriting selkies in another language. Python is not the bottleneck; the
  policy is.

## Anti-goals (a failure even if numbers improve)

- Text stays soft because the controller is too timid (bitrate pinned low on a
  good office link).
- New visible hitches from over-eager frame skipping.
- Breaking viewer (non-owner) tabs, seat hold, or reconnect behavior (PR #46).

## How (decided)

- **Delivery: monkeypatch from `agent/engine.py`**, the same pattern as
  `cap_still_raise`. Live iteration on the mini, no fork wheel. Each patch carries a
  `ponytail:` note naming the upstream issue/PR that deletes it.
- **Upstream:** once measured on the mini, open issues and PRs on
  `selkies-project/selkies` with the before/after numbers. Nothing is posted
  without the user's go.
- **Mechanisms**
  1. Owner shallow-pipe gate: apply `_room()`/`_lag()`-style gating to the owner
     relay with a time-based budget (≈100 ms beyond floor RTT, from
     `_ws_write_backlog` + ack RTT). Skip deltas while over budget, never anchors/IDR.
  2. Smooth rate control: replace halving with a delay-gradient controller.
     Target ≈ delivered rate while RTT is near floor. Proportional ease-off as
     queued delay grows. Gentle additive/×1.05 probe only when the path proves
     headroom. Must coexist with or replace `cap_still_raise`.
- **Deploy:** gated on the user's go. A restart kills the seat terminal, so the user
  triggers or approves restarts.

## Builder calls settled (Claude's calls, flagged for review)

- **Order:** the harness lands first and runs on unpatched 0.9.10 to produce the
  baseline. Then gate, then controller, each measured alone (one variable at a time).
- **Control law** (wraps `CongestionSteer.target`, tick stays on selkies' 0.5 s
  loop for v1). `q` = min RTT in tick window − floor (ms), `d` = delivered kbps:
  - `q < 30`: hold or probe. Raise ≤ ×1.05 per s, never past `known` capacity ×1.05
    (known = max delivered with q < 30; the `cap_still_raise` memory).
  - `30 ≤ q < 150`: target = d × (1 − q/300). Proportional ease-off, no hold.
  - `q ≥ 150`: target = d × 0.5 (real collapse, e.g. hotspot dip).
  - Floor/ceiling unchanged (the admin bitrate is the ceiling).
  Constants are starting points, tuned against the harness.
- **`cap_still_raise` is replaced, not stacked.** Its capacity memory moves into
  the new controller. One patch steers the rate, so the two can't fight.
- **Owner gate placement:** inside the owner's own `_VideoRelay` (`_forward`).
  Every client has its own relay and deque, so viewers are isolated by
  construction. Skips go through the existing `_lose` → `_repair` →
  `invalidate_reference` path. No new recovery code; anchors/IDR never skipped.
  The skip count is logged only. The controller steers on RTT, not skips.

## Measurement harness (part of Phase 1)

- Log one structured line per 0.5 s tick from the patched controller: RTT,
  floor, queued ms, delivered kbps, target kbps, skips. Parse it with a small script in
  `agent/tests` or `docs/spike` to produce the success table.
- Scripted session, ~5 min: idle → scroll long page → type in terminal → video
  clip. Run on office/home Wi-Fi. Hotspot run optional but wanted.
- Optional: `tc netem` on a client box to emulate hotspot jitter/loss for a
  repeatable A/B.

## Left to the builder

- Final controller constants. Moving to a faster tick (acks arrive every 50 ms)
  if 0.5 s proves too coarse in the harness.
- Test shape: pure-function unit tests for the controller (fake ack streams:
  steady, jitter, step-down, hotspot dip) in `agent/tests`.

## Phase 2 (later, separate design)

Rust in pixelflux: feed Wayland damage rects (already read, `pwcapture.rs:527`)
into per-region quality. VAAPI `VAEncROI` for AMD/Intel, the NVENC QP map
(exists, `fill_band_map`). Goal: sharp static text at near-zero bits.
