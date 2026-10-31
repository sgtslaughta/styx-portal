# Hold the display owner's video queue to the same lag gate other pages get

Target: selkies-project/selkies, `src/selkies/websockets_mode.py`, selkies 2.1.0.
Patch: `01-selkies-owner-lag-gate.patch` (`diff -u` against the 2.1.0 file; applies with `patch -p1` from the package parent dir).

## Problem

`_VideoRelay._forward` gates delta frames for pages that do not own the display: a frame is left out when the page has `VIDEO_RELAY_ROOM_FRAMES` frames in flight or the ping written behind its frames has gone unanswered more than `VIDEO_RELAY_LAG_SECONDS` past the round trip. The encoder then predicts past the gap (`_lose` -> `_repair`).

The page that owns the display skips all of that (`if self.server._owns_display(...): return True`). Its only bound is the relay budget (`VIDEO_RELAY_BUDGET_SECONDS`, 2 s of stream). On a jittery link (Wi-Fi, phone hotspot) a stall lets frames pile up in the server send path. When the link recovers the controlling viewer plays seconds of late video, and the RTT-based congestion controller sees the inflated round trip and cuts bitrate hard, so the picture also goes soft.

## Repro

1. One page controlling a display, video on the WebSocket (we run it behind a Cloudflare tunnel).
2. Client on a lossy or jittery link (we used hotel Wi-Fi tethered through a phone).
3. Scripted session of about 5 min: idle, scroll, type, video, idle.
4. Read the congestion log (`Congestion control[...]: video bitrate A -> B kbps`) and the per-tick queue (least ack round trip past the floor, less its serialization).

## Fix

Give the owner its own lag threshold, `VIDEO_RELAY_OWNER_LAG_SECONDS = 0.1`. In the owner branch of `_forward`:

- set `gauged = True` so the relay writes its pings behind the owner's frames (otherwise `_lag()` reads 0);
- send the frame if it is an anchor, a frame_num-wrap frame (`kept`), or `_lag()` is under the threshold;
- otherwise `_lose` and `_repair`, exactly as for a non-owner page.

No new recovery path: it reuses the existing reference-invalidation machinery. Key frames never reach `_forward`'s skip, and anchors and wrap frames always go.

## Evidence

Same scripted session, same link, before and after. The only change between runs is the gate (agent 0.9.12 vs 0.9.13). Raw data: `docs/spikes/2026-10-30-shallow-pipe/baseline-0.9.12.txt` and `after-gate-0.9.13.txt`.

| | no gate | owner gate |
|---|---|---|
| Bitrate cuts over 30% per 5 min | 6.45 | 0 |
| Max extra queue past floor | 735 ms | 42 ms |
| p99 extra queue | 116 ms | 31 ms |
| p90 extra queue | 15 ms | 6 ms |
| Frames reported lost per 5 min | 3.87 | 2.91 |
| Delivered-rate CV | 1.15 | 0.84 |
| Backpressure triggers | 9 | 2 |

Caveat: the gated run started at 5894 kbps (the page's last held rate) and the baseline started at the 16000 kbps ceiling, so part of the difference could be the start rate. One link, one session each; not a repeated trial.

## Risk / compat

- Behavior change only for the owning page, and only once its queue passes 100 ms past the round trip. On a clean link `_lag()` stays near 0 and nothing is skipped.
- Skipped deltas are recovered by the same reference-invalidation path non-owners use. If `_repair` returns None the caller falls back to a key frame, as today.
- The constant is a module-level default; it could be made a setting if you prefer.
- Our downstream copy is gated on `selkies.__version__ == "2.1.0"` and does nothing on other versions, since `_forward` is a whole-function replacement. Upstream would not need that.
- Not checked: owners behind a very slow link, where 100 ms may skip many frames and lean on key-frame recovery. Seat-mode multi-viewer handoff (owner changes mid-run) was used but not stress-tested.

## Testing

- Downstream: live session on the hotel Wi-Fi profile above (table). Our agent test suite covers the gate (`agent/tests`, calls `shallow_pipe.owner_gate`).
- Not run: upstream's own test suite (not checked out here). Suggested unit tests: owner with `_lag()` above threshold gets a delta skipped; anchor and `kept` frames still go; non-owner behavior unchanged.
- `python3 -m py_compile` passes on the patched file.
