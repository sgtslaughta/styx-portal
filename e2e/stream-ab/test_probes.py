import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probes  # noqa: E402


def test_cpu_percent():
    assert probes.cpu_percent(100, 150, 1.0, hz=100) == 50.0     # 50 ticks of 100 in 1 s
    assert probes.cpu_percent(100, 100, 0.0) == 0.0


def test_parse_stat_ticks():
    stat = "4242 (python3) S 1 2 3 4 5 6 7 8 9 10 120 30 0 0 20 0 1 0 5 6 7"
    assert probes.stat_ticks(stat) == 150


def test_summarize():
    s = [{"cpu": 10, "vcn": 20, "rss_mb": 100}, {"cpu": 30, "vcn": 40, "rss_mb": 120}]
    out = probes.summarize(s)
    assert out["cpu_mean"] == 20 and out["cpu_max"] == 30 and out["vcn_mean"] == 30
    assert out["rss_mb_max"] == 120 and out["rss_mb_growth"] == 20
    assert probes.summarize([]) == {}
