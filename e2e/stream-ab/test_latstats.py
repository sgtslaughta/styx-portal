import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import latstats as L  # noqa: E402


def test_percentiles_interpolate():
    v = list(range(1, 101))
    assert L.pct(v, 50) == 50.5 and L.pct(v, 100) == 100 and L.pct(v, 0) == 1
    assert round(L.pct(v, 95), 2) == 95.05 and L.pct([], 50) is None
    assert L.pct([7], 99) == 7


def test_summary_counts_over_100_and_jitter():
    s = L.summarize([50, 50, 50, 150])
    assert s["n"] == 4 and s["over100"] == 1 and s["max"] == 150
    assert round(s["std"], 2) == 43.30 and L.summarize([])["p50"] is None
    assert L.summarize([100])["over100"] == 0          # strictly slower than 100


def test_pacing_stalls_and_std():
    steady = [i * 8.333 for i in range(100)]
    p = L.pacing(steady)
    assert p["stalls"] == 0 and p["interval_std"] < 1e-6 and round(p["fps"]) == 120
    gappy = steady[:50] + [t + 70 for t in steady[50:]]
    assert L.pacing(gappy)["stalls"] == 1
    assert L.pacing([5])["fps"] is None


def test_sample_ms_requires_order():
    assert L.sample_ms({"t0": 10, "pres": 40.5}, "pres") == 30.5
    assert L.sample_ms({"t0": 10}, "pres") is None
    assert L.sample_ms({"t0": 10, "pres": 5}, "pres") is None


def test_analyse_parses_client_output():
    mk = lambda n, d, p: [{"t0": 100 * i, "dec": 100 * i + d, "pres": 100 * i + p} for i in range(n)]  # noqa: E731
    client = {"sink": "video", "sent": {"key": 11, "mouse": 5, "motion": 5}, "delivered": {"key": 11, "mouse": 4, "motion": 5},
              "presentedTimes": [i * 10 for i in range(20)], "samples": {
        "key": mk(10, 30, 45) + [{"t0": 0}],        # one missed sample
        "mouse": mk(5, 20, 35), "motion": mk(5, 25, 40)}}
    a = L.analyse(client)
    assert a["key"]["presented"]["p50"] == 45 and a["key"]["decoded"]["p50"] == 30
    assert a["key"]["missed"] == 1 and a["mouse"]["missed"] == 0
    assert round(a["key"]["miss_rate"], 3) == round(1 / 11, 3) and a["key"]["sent"] == 11
    assert a["mouse"]["sent"] - a["mouse"]["delivered"] == 1      # input lost, not detection missed
    row = L.flat("av1-60", "lan", client)
    assert row["legacy"]["latP50"] == 30 and row["pacing"]["stalls"] == 0


def test_table_has_a_line_per_input():
    row = L.flat("h264-120", "cf-tunnel", {"samples": {}, "presentedTimes": []})
    row["valid"] = False
    t = L.table([row]).splitlines()
    assert len(t) == 2 + 3 and "h264-120" in t[2] and t[2].endswith("| False |")


def test_misses_never_become_latency_values():
    raw = [{"t0": 0, "dec": None, "pres": None}, {"t0": 0, "dec": 3000, "pres": None}, {"t0": 5, "pres": 45}]
    a = L.analyse({"samples": {"key": raw}})
    assert a["key"]["presented"]["n"] == 1 and a["key"]["presented"]["p50"] == 40
    assert a["key"]["missed"] == 2 and a["key"]["presented"]["max"] == 40
