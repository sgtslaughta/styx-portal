import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cc_report  # noqa: E402

LINES = [
    "INFO:ws:STYX-CC primary q=0 floor=60 dlv=8000 rate=8000",
    "INFO:ws:STYX-CC primary q=30 floor=60 dlv=8000 rate=8000",
    "INFO:ws:Congestion control[primary]: video bitrate 16000 -> 4000 kbps (round trip 300 ms over a 60 ms floor, 8000 kbps delivered)",
    "INFO:ws:STYX-CC primary q=60 floor=60 dlv=7000 rate=4000",
    "INFO:ws:Display 'primary': frame 12 lost by a client; the encoder predicts past it.",
    "INFO:ws:STYX-CC primary q=180 floor=60 dlv=3000 rate=4000",
    "unrelated line",
]


def test_summarize():
    s = cc_report.summarize(LINES)
    assert s["ticks"] == 4
    assert s["q_floor_p50"] == 1.75
    assert s["cuts_gt30_per5m"] > 0
    assert s["lost_per5m"] > 0


def test_summarize_empty():
    assert cc_report.summarize([])["ticks"] == 0
