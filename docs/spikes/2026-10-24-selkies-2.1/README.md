# Spike: selkies 2.1.0 vs our seat refit (resize)

Question: can we move from selkies 2.0.0 → 2.1.0 without losing the
near-gapless GNOME-seat resize (warm standby selkies + transparent reconnect)?

## Answer

Yes — and it gets simpler and faster. selkies 2.1 reopens its stream socket
in place on a cut connection, so the injected reconnect proxy in `refit.py`
(`_PROXY_JS`, Blob/Worker wrappers) is no longer needed. Two gateway changes
make the native path beat today's shim:

1. **Refit = abort the socket** (client sees 1006 → 2.1 reconnects at once,
   attempt 1 has no backoff). A clean close with any non-reserved code waits
   ~400 ms backoff first.
2. **Hold the ws upgrade while `refit-request` is pending**, so the instant
   reconnect lands on the promoted standby, not the dying selkies (without it:
   lands on old process → close 1000 → 800 ms backoff).

## Results (gateway-side timing, 3 runs each)

| Variant | Reconnect arrives | First video frame | Page reload |
|---|---|---|---|
| 2.0.0 + current shim (prod today) | +108 ms | +143–146 ms | no |
| 2.1.0 + current shim | — | ~+600 ms | **yes** (shim never installs) |
| 2.1.0 native, close 4012 | +410 ms | +445–459 ms | no |
| **2.1.0 native, abort (1006) + gateway hold** | **+6–7 ms** | **+67–96 ms** | no |

Times are from the refit close. During the gap 2.1 keeps the last frame on
screen (no black, no overlay) — verified by screenshots.

## Why the drop-in upgrade breaks

- `refit.py` finds selkies' socket worker by the source text
  `new WebSocket(m.url)`: 1 hit in 2.0.0, **0 in 2.1.0** → proxy silently absent.
- 2.1 reserves close codes: **4001** = "Invalid token", reconnect disabled
  (our gateway uses 4001 for idle timeout); **4002** = "permission change",
  full page reload (our refit code). A close whose reason matches
  `/superseded/i` disables auto-reconnect and shows "Session opened elsewhere.
  Reload this page to take over."
- Any other close → in-place reconnect loop. Our busy refusal (4003) would
  therefore retry forever on 2.1; send it with reason `superseded` instead
  (2.1 then shows a near-identical "in use elsewhere" message).

## Upgrade plan (not done)

1. Gateway: refit → abort transport; hold upgrade while refit pending (spike
   code on this branch, `STYX_SPIKE_ABORT` gate to remove).
2. Idle close: not 4001 (pick reason/code 2.1 treats as final, e.g.
   `superseded`-style, or keep our overlay with a non-reconnecting code — test).
3. Busy refusal: reason `superseded`.
4. Delete `_PROXY_JS` + Blob/Worker wrappers + `socket_worker` strip from
   `refit.py`; keep HOLD_HTML for full loads.
5. Bump pins in `agent/enroll.sh` (selkies 2.1.0, pixelflux 2.2.1, pcmflux 2.2.0);
   review `--frame-ancestors` (now `'self'`) for the portal's `/w/{sub}` frame.
6. Verify on a real GNOME seat (GAME-01 first) **through Cloudflare + Traefik**:
   confirm an upstream abort still reaches the browser as 1006 (an
   intermediary that sends its own close code would cost the 400 ms backoff).
7. Fix the 3 gateway tests that assert close code 4002.

## Limits of this spike

- Xvfb + X11 capture, not the GNOME seat; the fake agent promotes instantly
  (real agent adds the in-place Mutter resize, ~100 ms — the hold covers it).
- Audio disabled; 2.1 claims playback state survives the reopen — untested.
- Immediate reopen applies to the first attempt only (`_t` resets after a
  connection lives 10 s); rapid back-to-back resizes fall to 400/800 ms backoff.

## Reproduce

`harness/`: `fake_agent.py` (Xvfb :150, selkies active+standby, real
`agent/gateway.py` on :8445, promotes on `refit-request`), `probe.mjs`
(Playwright: load, resize 1280x720→1600x900), `tsum.py` (gateway timings).
Needs venvs `v2.0.0` / `v2.1.0` next to `spike/` (see `run.sh`) and the e2e
`node_modules` symlinked in. `STYX_SPIKE_T=1` enables gateway timing prints.
