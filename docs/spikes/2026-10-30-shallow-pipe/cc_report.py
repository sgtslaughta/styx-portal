"""Summarize a selkies.log for the shallow-pipe A/B (spec success table).

    python3 cc_report.py ~/.local/share/styx-agent/logs/selkies.log [--tail N]
"""
import argparse
import re
import statistics

TICK = re.compile(r"STYX-CC \S+ q=(\d+) floor=(\d+) dlv=(\d+) rate=(\d+)")
CUT = re.compile(r"Congestion control\[.*?video bitrate (\d+) -> (\d+) kbps")
LOST = re.compile(r"frame \d+ lost by a client")
TICK_S = 0.5    # selkies' backpressure loop; the log carries no timestamps


def summarize(lines) -> dict:
    ratios, dlv, cuts, lost = [], [], 0, 0
    for line in lines:
        if m := TICK.search(line):
            q, floor, d = int(m[1]), int(m[2]), int(m[3])
            ratios.append((q + floor) / floor if floor else 1.0)
            dlv.append(d)
        elif m := CUT.search(line):
            cuts += int(m[2]) < 0.7 * int(m[1])
        elif LOST.search(line):
            lost += 1
    per5m = 300 / (len(ratios) * TICK_S) if ratios else 0.0
    q = statistics.quantiles(ratios, n=10) if len(ratios) > 1 else ratios or [0.0]
    return {
        "ticks": len(ratios),
        "q_floor_p50": statistics.median(ratios) if ratios else 0.0,
        "q_floor_p90": q[-1],
        "cuts_gt30_per5m": cuts * per5m,
        "lost_per5m": lost * per5m,
        "dlv_cv": statistics.pstdev(dlv) / statistics.mean(dlv) if dlv and statistics.mean(dlv) else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--tail", type=int, default=0, help="only the last N lines")
    a = ap.parse_args()
    with open(a.log, errors="replace") as f:
        lines = f.readlines()
    for k, v in summarize(lines[-a.tail:] if a.tail else lines).items():
        print(f"{k:16} {v:.2f}" if isinstance(v, float) else f"{k:16} {v}")


if __name__ == "__main__":
    main()
