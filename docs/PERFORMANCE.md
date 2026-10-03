# Workstation Gaming Performance

Styx Portal stream-settings knobs and host tuning to optimize gaming and interactive workloads.

## Stream Settings

Configure via **Settings → System → Workstations → Stream settings**:

- **FPS** — 60 default; 120 only with GPU + bandwidth headroom.
- **Quality (CRF)** — H.264 CRF, default 25. 15–20 for gaming quality; lower = more bandwidth.
- **Gaming mode** — full-motion encoding (`SELKIES_H264_STREAMING_MODE`); consistent latency under heavy motion, more bandwidth on static desktops. Turn on for game seats.
- **Sharpen static screen** — paint-over pass re-encodes idle screens at high quality (crisp text). Leave on.

## Host Tuning

The workstation agent (`styx_agent.py doctor`) checks and advises on the following:

- **NVIDIA persistence mode:** `sudo nvidia-smi -pm 1` removes GPU initialization stall on stream start.
- **CPU governor:** `sudo cpupower frequency-set -g performance` on dedicated gaming boxes locks the CPU to peak frequency.

## Operational Tips

- **Seat resolution:** GNOME seats stream at a fixed `seat_width` x `seat_height` (default 2560x1440); lower it per workstation on slow links or weak encoders.
- **Tab visibility:** The stream pauses when its tab is backgrounded and resumes on return (by design — prevents long-session memory growth). Refresh if a stream ever sticks.
- **Audio latency:** Audio adds 100–250 ms pipeline latency after settling; disable audio for competitive play.
- **GPU acceleration:** NVENC engages automatically when a render node exists; `doctor` shows `GPU render node`. CPU x264 fallback costs latency and quality.
