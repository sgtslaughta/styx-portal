# Workstation Gaming Performance

Styx Portal stream-settings knobs and host tuning to optimize gaming and interactive workloads.

## Stream Settings

Configure via **Settings → System → Workstations → Stream settings**:

- **FPS** — 60 default; 120 only with GPU + bandwidth headroom.
- **Quality (CRF)** — H.264 CRF, default 25. 15–20 for gaming quality; lower = more bandwidth.
- **Max bitrate (kbps)** — ceiling: the admin value is both the default and the maximum; viewers may lower it from the stream panel (floor 1000 kbps).
- **Gaming mode** — full-motion encoding (`SELKIES_H264_STREAMING_MODE`); consistent latency under heavy motion, more bandwidth on static desktops. Turn on for game seats.
- **Sharpen static screen** — paint-over pass re-encodes idle screens at high quality (crisp text). Leave on.

## Host Tuning

The workstation agent (`styx_agent.py doctor`) checks and advises on the following:

- **NVIDIA persistence mode:** `sudo nvidia-smi -pm 1` removes GPU initialization stall on stream start.
- **CPU governor:** `sudo cpupower frequency-set -g performance` on dedicated gaming boxes locks the CPU to peak frequency.

## Operational Tips

- **Seat resolution:** GNOME seats follow the owning browser's window size (device pixels), so a large HiDPI window streams a large frame; shrink the window or turn on the client's **HiDPI off** (CSS pixels) option to cut encode cost. The per-workstation **Full colour (4:4:4)** toggle sharpens text but runs on software x264 on VA-API GPUs (CPU, larger frames); leave it off on slow uplinks.
- **Tab visibility:** The stream pauses when its tab is backgrounded and resumes on return (by design — prevents long-session memory growth). Refresh if a stream ever sticks.
- **Audio latency:** Audio adds 100–250 ms pipeline latency after settling; disable audio for competitive play.
- **GPU acceleration:** NVENC engages automatically when a render node exists; `doctor` shows `GPU render node`. CPU x264 fallback costs latency and quality.
