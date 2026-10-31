# AV1 on radeonsi before VCN 5: signal the render size and crop in the web client

Two changes, two repos.
- `02a-pixelflux-av1-render-size.patch`: selkies-project/pixelflux, `pixelflux/src/encoders/vaapi/av1.rs` (git commit 83c0d82, branch `fix/vaapi-av1-render-size`, pushed to the author's fork only).
- `02b-selkies-av1-crop-client.patch`: selkies-project/selkies, `selkies_web/src/selkies-core.js` (the video worker).

## Problem

On a Radeon 780M (VCN 4, Mesa 26.0.8) the AV1 stream is larger than the source, because radeonsi writes its own sequence header and pads the coded size:

| source | decoded frame size |
|---|---|
| 1920x1080 | 1920x1082 |
| 1366x768 | 1408x768 |
| 1280x720 | 1280x720 |

(Height pads by 2 when it is 8 mod 16, width to a multiple of 64. Not 1088, which is what a plain 16-alignment would give.) The frame header pixelflux packs says `render_and_frame_size_different = 0`, so nothing in the stream gives the real picture size. H.264 and HEVC carry a crop / conformance window and are not affected.

Chromium's WebCodecs AV1 decoders ignore `render_size`, so the browser shows the padded frame: 1080p is squeezed by 2 rows; 1366 wide is stretched about 3% with padding visible at the right edge. Fixing the stream alone does not fix the browser.

## Repro

1. VA-API host with a pre-VCN-5 AMD GPU, pixelflux encoding AV1 (`av1enc`) at 1920x1080 or 1366x768.
2. Decode with FFmpeg `-vf trace_headers` (or `ffprobe`): `max_frame_height_minus_1 = 1081`, `render_and_frame_size_different = 0`, size reported 1920x1082.
3. In Chromium 156, a `VideoDecoder` output frame has `codedWidth/Height`, `displayWidth/Height` and `visibleRect` all at the padded size.

## Fix

1. pixelflux (`02a`): in the AV1 frame header write `render_and_frame_size_different = 1` plus `render_width_minus_1` / `render_height_minus_1` from the negotiated size, on every key and inter frame. 33 extra bits a frame; `bit_offset_qindex` moves by the same amount and the existing header test is updated. Correct by the AV1 spec; FFmpeg/mpv-style players then show the source aspect (SAR 541:540 at 1080p).
2. selkies web client (`02b`): crop the decoder output to the configured size before it reaches a sink, with `new VideoFrame(f, { visibleRect: { x: 0, y: 0, width, height } })`, then close the original. It is a no-op when the output already matches the configured size or is smaller, and falls back to the uncropped frame on error.

## Evidence

Chromium 156 headless, software dav1d. Mean absolute pixel error against the source (the codec's own loss is about 2.4):

| sink | region | as today | cropped |
|---|---|---|---|
| canvas `drawImage` | 1080p, bottom 32 rows | 6.2 | 2.3 |
| canvas `drawImage` | 1366x768, right 32 columns | 58.8 | 2.5 |
| `<video>` via track generator, objectFit fill | 1080p bottom rows | 6.2 | 2.4 |
| `<video>` via track generator, objectFit fill | 1366x768 right columns | 46.8 | 2.9 |

pixelflux: 60 frames at 1080p and 1366x768 through `VaapiEncoder::encode_host`. Before: `render_and_frame_size_different = 0` on all frames. After: 1, with render size 1919x1079 and 1365x767 (minus-1 values) on every frame. `cargo test --lib` 544 passed in default and `gpl` configs; `cargo test vaapi_ -- --ignored` 4/4 on the 780M; clippy `-D warnings`, rustfmt, codespell clean.

Downstream, the client crop is live in our patched selkies bundle (backup kept as `selkies-core-BGbb3Bx7.js.bak-av1crop`; the diff of installed vs backup is the same change as `02b`, applied to the built asset).

## Risk / compat

- pixelflux change affects only the VA-API AV1 path. NVENC writes its own headers and is untouched. It applies whether or not the driver pads; where it does not, render size equals frame size and decoders see no change.
- Client crop only triggers when a decoded frame is larger than the configured size, so H.264, HEVC and other drivers pass through unchanged. It needs `VideoFrame` `visibleRect` (Chromium 94+, Safari/Firefox support for the constructor option not tested).
- Version guard: none needed in the PR. Downstream we patch the built bundle of selkies 2.1.0 (asset `selkies-core-BGbb3Bx7.js`), so it must be redone when the asset hash changes.
- Not covered: VCN 5 (pads height to a multiple of 2 only; other widths unchecked), Intel and NVIDIA hosts, other AMD generations.

## Testing

Done: items under Evidence.
Not run: Chrome GPU (VA-API) decode path, the worker `VideoTrackGenerator` sink as a clean harness, Firefox, Safari, and the crop through a full upstream selkies build (verified on our installed bundle only). The `02b` patch is against `src/selkies-core.js` and was not built with the upstream toolchain.
