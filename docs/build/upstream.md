# Upstream contributions

Styx runs on [selkies](https://github.com/selkies-project/selkies) and
[pixelflux](https://github.com/selkies-project/pixelflux). Where we find a defect
or a missing behaviour we write it up and patch it upstream-style, keep the patch
in `docs/upstream/`, and carry a guarded runtime copy until upstream merges.

| # | Target | Problem | Our patch | Downstream carrier |
|---|--------|---------|-----------|--------------------|
| 01 | selkies `src/selkies/websockets_mode.py` (2.1.0) | The page that owns the display is exempt from the video lag gate, so on a jittery link frames pile up (up to the 2 s relay budget) and the congestion controller cuts bitrate hard | [write-up](../upstream/01-selkies-owner-lag-gate.md), [patch](../upstream/01-selkies-owner-lag-gate.patch): owner gets a 100 ms lag threshold and reuses the existing `_lose` / `_repair` path | `agent/shallow_pipe.py::owner_gate`, only on selkies 2.1.0 |
| 02a | pixelflux `src/encoders/vaapi/av1.rs` | VA-API AV1 on pre-VCN-5 AMD pads the coded frame and the AV1 header carries no render size | [patch](../upstream/02a-pixelflux-av1-render-size.patch): write `render_and_frame_size_different = 1` with the real size | wheel build (see [Agent](agent.md#seats)) |
| 02b | selkies web client (`selkies-core.js` video worker) | Chromium ignores the AV1 render size, so the picture is squeezed or stretched | [patch](../upstream/02b-selkies-av1-crop-client.patch), [write-up](../upstream/02-selkies-av1-crop.md): crop each decoded frame with `visibleRect` | `agent/bundle_patch.py`, re-applied on every agent start |

## Evidence summary

* **Owner lag gate** (hotel Wi-Fi profile, one session each, agent 0.9.12 vs 0.9.13): bitrate cuts over 30% per 5 min 6.45 -> 0; max extra queue 735 -> 42 ms; p99 116 -> 31 ms. Caveat: different start rates; not a repeated trial.
* **AV1 render size / crop** (Chromium 156, software dav1d): mean absolute pixel error in the padded region fell from 6.2-58.8 to 2.3-2.9 (the codec's own loss is about 2.4). pixelflux `cargo test --lib` and clippy clean.

## Related, tracked upstream

* Still-screen bitrate raise (the "poor connection" sawtooth): selkies#489, worked around by `engine.cap_still_raise`.
* AV1 crop in the web client: selkies#496 (referenced from `bundle_patch.py`).
* Scale/pointer mapping on a scaled seat: pixelflux#55.

## How to add one

1. Reproduce and measure with the [stream harness](streaming.md#latency-and-ab-harness-e2estream-ab).
2. Write `docs/upstream/NN-short-name.md`: target and version, problem, repro, fix, evidence, risk and compat, testing (what was and was not run).
3. Add the `.patch` (`diff -u` against the pinned upstream version).
4. Carry it downstream behind a **version guard** and mark it `ponytail:` so it can be dropped when upstream merges.
