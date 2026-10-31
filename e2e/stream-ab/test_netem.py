import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import netem  # noqa: E402


def test_rate_limits_delivery():
    s = netem.Shaper(netem.Profile(mbps=8, base_ms=0, jitter_ms=0), seed=1)
    t = [s.deliver_at(1_000_000, 0.0) for _ in range(3)]     # 1 MB each at 1 MB/s
    assert [round(x, 3) for x in t] == [1.0, 2.0, 3.0]


def test_order_preserved_under_jitter():
    s = netem.Shaper(netem.Profile(mbps=0, base_ms=20, jitter_ms=70), seed=7)
    t = [s.deliver_at(1000, i * 0.001) for i in range(200)]
    assert t == sorted(t) and min(t) >= 0.020


def test_collapse_window_slows_link():
    p = netem.Profile(mbps=40, base_ms=0, jitter_ms=0, collapse_every_s=10, collapse_for_s=2, collapse_mbps=1)
    s = netem.Shaper(p, seed=1)
    assert s.rate_bps(5.0) == 40e6 and s.rate_bps(10.5) == 1e6 and s.rate_bps(12.5) == 40e6


def test_profiles_exist():
    assert {"lan", "office", "hotel", "hotspot"} <= set(netem.PROFILES)


def test_outage_holds_data_until_link_returns():
    p = netem.Profile(mbps=8, base_ms=0, jitter_ms=0, drop_at_s=30, drop_for_s=10)
    s = netem.Shaper(p, seed=1)
    assert round(s.deliver_at(1000, 29.0), 3) == 29.001       # before: normal
    assert round(s.deliver_at(1000, 31.0), 3) == 40.001       # during: held until 40 s
    assert round(s.deliver_at(1000, 45.0), 3) == 45.001       # after: normal


def test_outage_profiles_exist():
    assert {"drop3", "drop10", "drop30"} <= set(netem.PROFILES)
    assert netem.PROFILES["drop30"].drop_for_s == 30


def test_new_profiles():
    P = netem.PROFILES
    assert P["lan"].base_ms * 2 <= 1 and P["lan"].loss_pct == 0
    assert P["cf-tunnel"].loss_pct == 0
    assert 50 <= 2 * P["cf-tunnel"].base_ms + P["cf-tunnel"].jitter_ms / 2 <= 56    # measured median RTT 52.8 ms
    assert P["wifi-loss"].loss_pct == 0.5 and P["wifi-loss"].base_ms == P["cf-tunnel"].base_ms
    assert {"office", "hotel"} <= set(P)


def test_loss_adds_stalls_and_keeps_order():
    p = netem.Profile(0, 20, 0, loss_pct=0.5, retrans_ms=80)
    s = netem.Shaper(p, seed=3)
    t = [s.deliver_at(14000, i * 0.01) for i in range(2000)]    # 10 packets per write
    assert t == sorted(t)
    stalled = sum(1 for i, x in enumerate(t) if x - i * 0.01 > 0.09)
    assert 40 < stalled < 400           # ~5% of writes lose a packet; later ones queue behind


def test_no_loss_profile_draws_nothing():
    a = netem.Shaper(netem.PROFILES["cf-tunnel"], seed=1)
    assert a.penalty_ms(1_000_000) == 0
