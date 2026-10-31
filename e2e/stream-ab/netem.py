"""Userspace network emulator for the stream A/B harness: a TCP proxy that
shapes the server->client direction (rate, one-way delay + jitter, periodic
collapses), order-preserving like a TCP path. TLS passes through untouched.

    python3 netem.py --profile hotel --listen 18443 --target 127.0.0.1:8443

Profiles come from 2026-10-30 measurements: hotel Wi-Fi speed test 45 Mbps
down, latency 23 ms idle / 54 ms loaded, jitter 23 / 70 ms; the stream saw
the path collapse to <1 Mbps for seconds at a time.
ponytail: one shared shaper per proxy (like one access link); uplink gets
the base delay only, input is tiny.
"""
import argparse
import asyncio
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    mbps: float                 # 0 = unlimited
    base_ms: float
    jitter_ms: float            # extra delay drawn uniformly from [0, jitter_ms]
    collapse_every_s: float = 0
    collapse_for_s: float = 0
    collapse_mbps: float = 0
    drop_at_s: float = 0        # one outage: nothing gets through for drop_for_s,
    drop_for_s: float = 0       # what was sent meanwhile arrives after (TCP retransmits)
    loss_pct: float = 0         # per-packet loss; a TCP path shows it as a retransmit stall
    retrans_ms: float = 0       # ...of this long (RTT + RTO slack), holding up everything behind it
    burst_p: float = 0          # per-write chance of a Wi-Fi jitter burst
    burst_ms: float = 0         # ...of up to this much extra delay


PROFILES = {
    "lan": Profile(0, 0.25, 0),            # ~0.5 ms RTT, no loss
    "office": Profile(100, 5, 2),
    "hotel": Profile(45, 20, 70, collapse_every_s=60, collapse_for_s=3, collapse_mbps=1),
    "hotspot": Profile(10, 40, 30, collapse_every_s=30, collapse_for_s=2, collapse_mbps=2),
    # Cloudflare tunnel hairpin to g.jmolabs.dev, measured 2026-10-31 (20x curl, TCP connect c and
    # time_starttransfer t): connect median 13.5 ms (9-24); app-level RTT = t - 2c: median 52.8 ms,
    # p10-p90 46-68 ms, min 43, max 74, sd 8. Here: 20 ms each way + uniform 0-25 ms down = 52.5 ms median RTT.
    "cf-tunnel": Profile(0, 20, 25),
    # cf-tunnel on flaky Wi-Fi: 0.5% packet loss (retransmit stall ~1.5 RTT) and jitter bursts to 80 ms.
    "wifi-loss": Profile(0, 20, 25, loss_pct=0.5, retrans_ms=80, burst_p=0.02, burst_ms=80),
    # Wi-Fi -> cellular handoff, tunnel in a dead zone: an office link that vanishes once.
    "drop3": Profile(100, 5, 2, drop_at_s=40, drop_for_s=3),
    "drop10": Profile(100, 5, 2, drop_at_s=40, drop_for_s=10),
    "drop30": Profile(100, 5, 2, drop_at_s=40, drop_for_s=30),
}


class Shaper:
    def __init__(self, profile: Profile, seed: int = 0):
        self.p, self.rng = profile, random.Random(seed)
        self.free_at = self.last = 0.0

    def rate_bps(self, t: float) -> float:
        p = self.p
        if p.collapse_every_s and t >= p.collapse_every_s and t % p.collapse_every_s < p.collapse_for_s:
            return p.collapse_mbps * 1e6
        return p.mbps * 1e6

    def penalty_ms(self, nbytes: int) -> float:
        """Loss stall and jitter burst for one write. No rng draws when both are off."""
        p, extra = self.p, 0.0
        if p.loss_pct:
            pkts = max(1, nbytes // 1400)
            if self.rng.random() < 1 - (1 - p.loss_pct / 100) ** pkts:
                extra += p.retrans_ms
        if p.burst_p and self.rng.random() < p.burst_p:
            extra += self.rng.uniform(0, p.burst_ms)
        return extra

    def deliver_at(self, nbytes: int, now: float) -> float:
        """When `nbytes` written at `now` reach the far end."""
        start = max(now, self.free_at)
        p = self.p
        if p.drop_for_s and p.drop_at_s <= start < p.drop_at_s + p.drop_for_s:
            start = p.drop_at_s + p.drop_for_s
        rate = self.rate_bps(start)
        self.free_at = start + (nbytes * 8 / rate if rate else 0.0)
        extra = self.penalty_ms(nbytes)
        t = self.free_at + (self.p.base_ms + self.rng.uniform(0, self.p.jitter_ms) + extra) / 1000
        self.last = max(t, self.last)        # a TCP path never reorders
        return self.last


async def _pump(reader, writer, delay_of):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    async def send():
        while (item := await queue.get()) is not None:
            at, data = item
            await asyncio.sleep(max(0.0, at - loop.time()))
            writer.write(data)
            await writer.drain()
        writer.close()

    sender = asyncio.create_task(send())
    try:
        while data := await reader.read(65536):
            queue.put_nowait((delay_of(len(data)), data))
    finally:
        queue.put_nowait(None)
        await sender


async def serve(profile: Profile, listen: int, host: str, port: int, seed: int = 0):
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    shaper = Shaper(profile, seed)

    def down(n):
        return t0 + shaper.deliver_at(n, loop.time() - t0)

    def up(_n):
        return loop.time() + profile.base_ms / 1000

    async def handle(cr, cw):
        try:
            sr, sw = await asyncio.open_connection(host, port)
        except OSError:
            cw.close()
            return
        await asyncio.gather(_pump(cr, sw, up), _pump(sr, cw, down), return_exceptions=True)

    server = await asyncio.start_server(handle, "127.0.0.1", listen)
    async with server:
        await server.serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=PROFILES, default="lan")
    ap.add_argument("--listen", type=int, default=18443)
    ap.add_argument("--target", default="127.0.0.1:8443")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    host, port = a.target.rsplit(":", 1)
    asyncio.run(serve(PROFILES[a.profile], a.listen, host, int(port), a.seed))


if __name__ == "__main__":
    main()
