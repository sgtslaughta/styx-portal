"""Soak: the harness workload over and over on the live settings for N minutes,
watching for slow failures a 2-minute A/B can't see: memory growth (selkies
RSS, GPU VRAM/GTT), selkies crashes (non-zero exits, e.g. the rc=-6 aborts of
2026-10-20), and agent watchdog restarts.

    python3 soak.py --minutes 90 [--profile office]

Results: results/soak-<stamp>.json (per-cycle rows + 10 s memory series) and .md.
"""
import argparse
import json
import re
import time

import ab
import probes

EXIT = re.compile(r"selkies exited rc=(-?\d+)")


def crashes(lines) -> int:
    return sum(1 for line in lines if (m := EXIT.search(line)) and m[1] != "0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=90)
    ap.add_argument("--profile", default="office")
    a = ap.parse_args()
    user, pw = ab.creds()
    since, end = time.strftime("%Y-%m-%d %H:%M:%S"), time.time() + a.minutes * 60
    trend, rows, firefox = probes.Sampler(every=10), [], ab.open_workload()
    trend.start()
    try:
        time.sleep(5)
        while time.time() < end:
            rows.append(ab.run_one("live", a.profile, user, pw))
            print(json.dumps({k: rows[-1].get(k) for k in (
                "codec", "valid", "watchdog", "latP50", "maxGapMs", "rss_mb_max", "gtt_mb_max")}), flush=True)
            if rows[-1]["foreign"]:
                print("ABORT: a user tab connected; yielding the seat", flush=True)
                break
    finally:
        summary = trend.stop()
        firefox.terminate()
    journal = ab.journal_since(since)
    summary |= {"minutes": round(a.minutes), "cycles": len(rows), "crashes": crashes(journal),
                "watchdog": ab.watchdog_restarts(journal),
                "latP50_mean": round(sum(r.get("latP50") or 0 for r in rows) / max(1, len(rows)))}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (ab.HERE / f"results/soak-{stamp}.json").write_text(
        json.dumps({"summary": summary, "rows": rows, "trend": trend.samples}, indent=1))
    (ab.HERE / f"results/soak-{stamp}.md").write_text(
        "\n".join(f"- {k}: {v}" for k, v in summary.items()) + "\n\n" + ab.table(rows) + "\n")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
