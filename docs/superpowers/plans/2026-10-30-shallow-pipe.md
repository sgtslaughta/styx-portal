# Shallow Pipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the controlling tab's video queue near the path floor and replace selkies' halving sawtooth with smooth delay-proportional rate control, measured before/after.

**Architecture:** Three runtime monkeypatches of selkies 2.1, installed from `agent/engine.py:seat_selkies_main` like the existing `cap_still_raise`. They live in a new `agent/shallow_pipe.py`: (1) a per-tick trace of selkies' congestion loop plus an offline report script, (2) an owner lag gate on `_VideoRelay._forward`, (3) a delay-gradient `CongestionSteer.target` that replaces `cap_still_raise`. Each patch is measured live on the mini before the next one lands.

**Tech Stack:** Python 3.12+/3.14 (agent venv), selkies 2.1.0, pytest.

**Spec:** `docs/superpowers/specs/2026-10-30-shallow-pipe-design.md`

## Global Constraints

- Video stays on WebSocket over the Cloudflare tunnel. No UDP/WebRTC, no encoder (pixelflux) changes.
- The owner gate never skips anchors, IDR, or `kept` frames (the H.264 frame_num wrap). Skips go only through the existing `_lose` → `_repair` path.
- Only the owner (controlling tab) relay changes. Viewer relays keep upstream behavior.
- Starting constants (tune later via harness): `OWNER_LAG_S = 0.1`; controller `CALM_MS = 30`, `COLLAPSE_MS = 150`, `EASE_MS = 300`, `PROBE = 1.05` per s, `COLLAPSE_CUT = 0.5`.
- Every patch has a `ponytail:` note naming its upstream deletion trigger (selkies-project/selkies issue/PR, number TBD at posting).
- Each task bumps `AGENT_VERSION` in `agent/styx_agent.py` plus the 3 asserts in `agent/tests/test_styx_agent.py`: Task 1 → 0.9.11, Task 2 → 0.9.12, Task 3 → 0.9.13.
- Deploys and restarts happen only on the user's go. A restart kills the seat terminal. Stage files to `~/.local/share/styx-agent/` with a `backup-YYYYMMDD-pre<ver>/` copy, and the user triggers the restart.
- Keep files under 500 lines. `agent/engine.py` is at 395; new code goes in `agent/shallow_pipe.py`.
- Gates: `backend/.venv/bin/python -m pytest agent/tests -q` all pass; `backend/.venv/bin/python -m ruff check agent/` clean.

## Review Focus

1. **Still screen (caret blink, no motion):** no trace spam, no rate change. The controller must treat app-limited ticks (offered < 0.5 × target) as "hold", never as capacity. Covered in Task 3's test `test_still_screen_holds`.
2. **Owner with no pong yet (`rtt_floor is None`, `_lag()` returns 0):** the gate must pass frames, never block a fresh connection. Covered in Task 2's test `test_owner_without_floor_passes`.
3. **Owner switches mid-stream (seat hold handoff, PR #46):** the gate reads ownership per frame, so a demoted owner falls back to the viewer rules. Covered in Task 2's test `test_viewer_rules_unchanged`.
4. **Hotspot collapse (q ≥ 150 ms for several ticks):** cut once, then no further cut while the queue drains (no ratchet to floor). Covered in Task 3's test `test_collapse_cuts_once_then_holds`.
5. **Reconnect after STOP/close:** the trace wrapper must tolerate `display_state` missing `link_steer`/`link_acks` (early return upstream). Covered in Task 1's test `test_trace_tolerates_empty_state`.

---

### Task 1: Trace + report harness, baseline

**Files:**
- Create: `agent/shallow_pipe.py`
- Create: `docs/spikes/2026-10-30-shallow-pipe/cc_report.py`
- Modify: `agent/engine.py:258-261` (install `trace_steer` next to `cap_still_raise`)
- Modify: `agent/styx_agent.py:19`, `agent/tests/test_styx_agent.py` (0.9.11)
- Test: `agent/tests/test_shallow_pipe.py`, `docs/spikes/2026-10-30-shallow-pipe/test_cc_report.py`

**Interfaces:**
- Produces: `shallow_pipe.queue_ms(display_state: dict) -> float | None` returns the least queued round trip among acks newer than `display_state['link_tick_at']`, minus `rtt_floor_ms`, using selkies' `_queued_round_trips` and `_path_rate`. None if there are no acks or no floor. It must be called **before** the original (which advances `link_tick_at`).
- Produces: `shallow_pipe.trace_steer(server_cls) -> None` wraps `server_cls._steer_bitrate_to_link`. It computes `q = queue_ms(state)`, stores it as `state.setdefault('link_steer', CongestionSteer()).styx_q_ms = q` (import `CongestionSteer` from `selkies.stream_server`; upstream reuses the same object via `setdefault`), calls the original, then, when `q is not None`, logs one line on logger `"ws"` at INFO:
  `STYX-CC {display_id} q={q:.0f} floor={floor:.0f} dlv={state.get('link_delivered_bps',0)/1000:.0f} rate={state.get('link_kbps',0):.0f}`
- Produces: `cc_report.summarize(lines: list[str]) -> dict` with keys `ticks`, `q_floor_p50`, `q_floor_p90` (ratio `(q+floor)/floor`), `cuts_gt30_per5m`, `lost_per5m`, `dlv_cv`. Cuts come from upstream `Congestion control[...]: video bitrate A -> B` lines where B < 0.7·A. Losses come from `frame N lost by a client`. Duration is the span of STYX-CC timestamps; when lines have no timestamps, count ticks × 0.5 s. CLI: `python cc_report.py <selkies.log> [--tail N]` prints the dict as an aligned table.

- [ ] **Step 1: Write failing tests**
  - `test_trace_sets_steer_q`: after the traced call, `state['link_steer'].styx_q_ms == 30`.
  - `test_queue_ms_least_minus_floor`: state with `rtt_floor_ms=60`, `link_tick_at=0`, `link_acks=[(1,100,1000),(2,90,2000),(3,120,3000)]`. Monkeypatch `selkies.websockets_mode._queued_round_trips` to return `[100,90,120]` → `queue_ms == 30`.
  - `test_trace_tolerates_empty_state`: fake server class whose `_steer_bitrate_to_link` returns None. After `trace_steer`, calling it with `{}` raises nothing and logs nothing (use `caplog`).
  - `test_trace_logs_line`: same fake class with the state from the first test → one record matching `^STYX-CC primary q=30 floor=60 `.
  - `test_summarize` (in the spike dir): 4 STYX-CC lines (q=0,30,60,180, floor=60), 1 cut line `16000 -> 4000`, 1 lost line → `q_floor_p50 == 1.75` (`statistics.median` of ratios 1.0, 1.5, 2.0, 4.0), `cuts_gt30_per5m > 0`, `lost_per5m > 0`.
- [ ] **Step 2: Run, verify fail:** `backend/.venv/bin/python -m pytest agent/tests/test_shallow_pipe.py docs/spikes/2026-10-30-shallow-pipe -q` → ImportError.
- [ ] **Step 3: Implement** `queue_ms`, `trace_steer`, `summarize` plus CLI (stdlib only: `re`, `statistics`, `argparse`). In `seat_selkies_main`, add `from selkies.websockets_mode import DataStreamingServer` and `shallow_pipe.trace_steer(DataStreamingServer)`. Add a ponytail note: `trace is for the Phase 1 A/B; drop or gate behind a setting once tuned`.
- [ ] **Step 4: Run, verify pass**, plus the full agent suite and ruff (Global Constraints gates).
- [ ] **Step 5: Bump 0.9.11, commit** `feat(agent): congestion trace + cc_report harness (0.9.11)`.
- [ ] **Step 6: Baseline (needs the user).** Stage the files and ask the user to restart. The user runs the scripted session (~5 min: idle 30 s → scroll a long web page 60 s → type in a terminal 60 s → play a video 60 s → idle). Then run `python3 docs/spikes/2026-10-30-shallow-pipe/cc_report.py ~/.local/share/styx-agent/logs/selkies.log --tail 20000`. Save the output to `docs/spikes/2026-10-30-shallow-pipe/baseline-0.9.11.txt`, noting the network (office/home/hotspot). Commit `docs(spike): shallow pipe baseline`.

### Task 2: Owner lag gate

**Files:**
- Modify: `agent/shallow_pipe.py`, `agent/engine.py` (install), version → 0.9.12
- Test: `agent/tests/test_shallow_pipe.py`

**Interfaces:**
- Consumes: Task 1 module.
- Produces: `shallow_pipe.OWNER_LAG_S = 0.1`, `shallow_pipe.owner_gate(relay_cls) -> None` replaces `relay_cls._forward` with a copy of upstream `_forward` (selkies 2.1.0 `websockets_mode.py:1285-1310`) whose owner branch becomes:
  ```python
  if self.server._owns_display(self.ws, self.display_id):
      self.gauged = True                      # owner pings behind its frames too, so _lag() reads
      if kept or anchor or self._lag() < OWNER_LAG_S:
          return True
      self._lose(frame_id)
      return self._repair()
  ```
  Every other line stays verbatim. Check `selkies.__version__` (or the dist version) == `2.1.0` at install. If it differs, log a warning and skip the patch, since a stale copy of `_forward` is worse than none.

- [ ] **Step 1: Write failing tests.** Build a fake relay class with the attributes `_forward` reads (`numbered`, `since_key`, `sent`, `lost_first`, `server`, `ws`, `display_id`, `gauged`) and stub methods `_lose`, `_repair` (record + return False), `_lag`, `_room`, `_anchor_room`, `_end_lost`.
  - `test_owner_over_lag_skips_delta`: owner, `_lag()=0.2`, delta → returns False and `_lose` called with the frame id.
  - `test_owner_under_lag_passes`: `_lag()=0.05` → True.
  - `test_owner_without_floor_passes`: `_lag()=0.0` → True.
  - `test_owner_anchor_and_kept_never_skipped`: `_lag()=5` with `anchor=True` → True; with `since_key % FRAME_NUM_WRAP == 0` and `numbered=True` → True.
  - `test_owner_sets_gauged`: after one call, `gauged is True`.
  - `test_viewer_rules_unchanged`: non-owner with `_room()=False`, delta → `_lose` called (upstream behavior).
  - `test_version_mismatch_skips_patch`: with the version monkeypatched to `"2.2.0"`, `owner_gate(cls)` leaves `cls._forward` unchanged.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** `owner_gate`. Install it in `seat_selkies_main` via `from selkies.websockets_mode import _VideoRelay`. Ponytail note: `copy of upstream _forward; drop when selkies gates the owner (issue TBD)`.
- [ ] **Step 4: Run, verify pass** + gates.
- [ ] **Step 5: Bump 0.9.12, commit** `feat(agent): shallow pipe gate for the controlling tab (0.9.12)`.
- [ ] **Step 6: Measure (needs the user).** Same session and network as the baseline. Save to `after-gate-0.9.12.txt` and commit. If `lost_per5m` is more than 2× the baseline, raise `OWNER_LAG_S` to 0.15 and re-measure before Task 3.

### Task 3: Delay-gradient controller (replaces `cap_still_raise`)

**Files:**
- Modify: `agent/shallow_pipe.py`, `agent/engine.py` (remove the `cap_still_raise` function and its install, install `smooth_steer`), version → 0.9.13
- Modify: `agent/tests/test_engine.py` (delete the `cap_still_raise` tests at ~line 285 onward and the `_Steer` fake)
- Test: `agent/tests/test_shallow_pipe.py`

**Interfaces:**
- Consumes: `self.styx_q_ms` on the steer, set by Task 1's `trace_steer` before each tick.
- Produces: `shallow_pipe.smooth_steer(steer_cls) -> None` replaces `steer_cls.target` (same signature as upstream `CongestionSteer.target(self, current, ceiling, floor, goodput_bps, loss, now, queue_s=None, offered_bps=None) -> float`). It keeps `self.styx_known_kbps` (max delivered kbps seen on a calm moving tick) and `self.styx_hold_until`.

Control law (`q = getattr(self, 'styx_q_ms', None)`, `d = goodput_bps/1000`, `moving = offered_bps is None or offered_bps >= current*1000*APP_LIMITED`, `dt` from `self._tick_at` exactly as upstream: `1.0` on the first tick, else `now - _tick_at` clamped to [0, 2]; update `_tick_at = now` every call):
```text
if q is None or not moving:            hold: return clamp(current)
if now < styx_hold_until:              return clamp(current)          # draining after a collapse
if q >= COLLAPSE_MS:                   styx_hold_until = now + 2*q/1000
                                       return clamp(min(current, d*COLLAPSE_CUT) if d>0 else current*COLLAPSE_CUT)
if q >= CALM_MS:                       return clamp(min(current, d*(1 - q/EASE_MS)))
# calm
known = styx_known_kbps = max(styx_known_kbps or 0, d)
return clamp(min(current*PROBE**dt, known*PROBE) if known else current*PROBE**dt)
clamp(x) = max(floor, min(ceiling, x))
```

- [ ] **Step 1: Write failing tests** (drive `target()` directly with `styx_q_ms` set per tick, `ceiling=16000`, `floor=1000`):
  - `test_calm_probes_gently`: q=0, d=8000, offered=8000 kbps, current=8000, 10 ticks 0.5 s apart → every result ≤ 8400 (`known*1.05`), and the first tick > 8000.
  - `test_ease_is_proportional`: q=60, d=10000 → `10000*(1-60/300) == 8000`.
  - `test_ease_never_raises`: q=60, current=5000, d=10000 → 5000.
  - `test_collapse_cuts_once_then_holds`: q=200, d=8000 → 4000. The next tick q=200 at now+0.2 → still 4000 (hold).
  - `test_still_screen_holds`: offered=100 kbps with current 8000 → returns 8000 unchanged, `styx_known_kbps` unchanged.
  - `test_no_measure_holds`: `styx_q_ms` absent → current.
  - `test_never_below_floor_or_above_ceiling`: q=1000, d=10 → 1000; calm with d=50000 → ≤ 16000.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement** `smooth_steer` plus the constants from Global Constraints. In `seat_selkies_main`, replace `cap_still_raise(CongestionSteer)` with `shallow_pipe.smooth_steer(CongestionSteer)`. Delete `cap_still_raise` and its tests. Ponytail note: `replaces selkies' halving steer; drop once upstream adopts delay-proportional backoff (issue TBD; also closes selkies#489)`.
- [ ] **Step 4: Run, verify pass** + gates.
- [ ] **Step 5: Bump 0.9.13, commit** `feat(agent): delay-proportional congestion control, replaces cap_still_raise (0.9.13)`.
- [ ] **Step 6: Measure (needs the user).** Same session. Save to `after-steer-0.9.13.txt` and write `docs/spikes/2026-10-30-shallow-pipe/RESULTS.md`: a table of baseline vs gate vs steer against the spec's success targets, the user's subjective verdict, and the constants used. Commit `docs(spike): shallow pipe results`.

### Task 4: Upstream packaging (after the user approves results)

**Files:**
- Create: `docs/spikes/2026-10-30-shallow-pipe/upstream-issue.md` (draft; nothing is posted without the user's go)

- [ ] **Step 1:** Draft one selkies issue covering the owner gate and the delay-proportional steer. Include the RESULTS table, the trace format, and links to the patch code. Reference selkies#489.
- [ ] **Step 2:** Ask the user before posting or forking. After posting, update the `ponytail:` notes with the issue number and commit `docs(agent): link upstream issue in shallow pipe patches`.
