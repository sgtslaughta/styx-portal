"""Gaming latency suite: every variant x network profile, input-to-photon, unattended.

    python3 ab.py --suite latency [--quick] [--dry-run]

Per variant: write stream-override.json, restart only selkies, warm up, then one latency.mjs run per
profile (netem.py in front of the gateway). Whatever happens, the original override file is put back
and selkies restarted onto it. Results: results/<stamp>-latency.json and .md (latstats.table).
"""
import json
import time
from pathlib import Path

import latstats

SUITE_VARIANTS = ["av1-60", "av1-120", "h264-60", "h264-120", "av1-60-bp8"]    # hevc-120: see ab.VARIANTS
SUITE_PROFILES = ["lan", "cf-tunnel", "wifi-loss"]
QUICK = (["av1-60", "h264-120"], ["lan", "cf-tunnel"])
MIN_SAMPLES = 90                      # presented samples per input kind for a cell to count
CODEC = {"av1enc": ("AV1",), "h265enc": ("HEVC", "H265"), "h264enc": ("H264",)}
WARMUP_ARGS = ("--n=5",)
CELL_TIMEOUT = 420
# Rough per-sample cost (s): mean 275 ms wait + the profile's typical input-to-photon.
SAMPLE_S = {"lan": 0.32, "cf-tunnel": 0.42, "wifi-loss": 0.5}
FIXED_S = 4 + 4 + 4.5 + 17 + 6       # proxy + page load + baselines + pacing phase + teardown/probes
RESTART_S = 25                       # restart selkies + 5 s settle + warm-up (5 samples x 3)


def select(quick: bool, variants: str | None, profiles: str | None) -> tuple:
    v, p = (list(QUICK[0]), list(QUICK[1])) if quick else (SUITE_VARIANTS, SUITE_PROFILES)
    return (variants.split(",") if variants else v), (profiles.split(",") if profiles else p)


def cell_seconds(profile: str, n: int = 100) -> float:
    return 3 * (n + 1) * SAMPLE_S.get(profile, 0.45) + FIXED_S


def estimate_s(variants: list, profiles: list, repeats: int = 1) -> float:
    return sum(RESTART_S + sum(cell_seconds(p) * repeats for p in profiles) for _ in variants) + 60


def format_plan(variants: list, profiles: list, repeats: int = 1) -> str:
    import ab
    lines = ["latency suite plan (dry run, nothing started):"]
    for v in variants:
        lines.append(f"  {v}: selkies {' '.join(ab.VARIANTS[v])}")
        lines += [f"      x {p}" + (f" (x{repeats})" if repeats > 1 else "") for p in profiles]
    n = len(variants) * len(profiles) * repeats
    lines.append(f"{n} cells x 3 inputs x 100 samples + 15 s pacing each; est. wall time "
                 f"{estimate_s(variants, profiles, repeats) / 60:.0f} min")
    lines.append("results -> results/<stamp>-latency.json and .md; override restored at the end")
    return "\n".join(lines)


def expected(args: list) -> tuple:
    """(codec tokens, fps) a variant's flags should produce, to check against selkies' own settings line."""
    enc = next(a.split("=", 1)[1].split(",")[0] for a in args if a.startswith("--encoder="))
    fps = next(int(a.split("=", 1)[1].split(",")[0]) for a in args if a.startswith("--framerate="))
    return CODEC[enc], fps


def problems(args: list, ab_row: dict, flat: dict) -> list:
    """Why a cell does not measure its variant (empty = valid)."""
    out = []
    codec, fps = expected(args)
    if not any(c in str(ab_row.get("codec", "")) for c in codec) or "VAAPI" not in str(ab_row.get("codec", "")):
        out.append(f"codec {ab_row.get('codec')} != {codec[0]} VAAPI")
    if ab_row.get("fps") is not None and abs(ab_row["fps"] - fps) > 1:
        out.append(f"fps {ab_row['fps']} != {fps}")
    for k in latstats.KINDS:
        if (flat.get(k) or {}).get("n", 0) < MIN_SAMPLES:
            out.append(f"{k}: {(flat.get(k) or {}).get('n', 0)} presented samples")
    if flat.get("error"):
        out.append("client error")
    if not ab_row.get("valid"):
        out.append("foreign client / watchdog restart")
    return out


def write_results(rows: list, res: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (res / f"{stamp}-latency.json").write_text(json.dumps(rows, indent=1))
    (res / f"{stamp}-latency.md").write_text(latstats.table(rows) + "\n")
    return res / f"{stamp}-latency.md"


def run(ab, variants: list, profiles: list, repeats: int = 1) -> None:
    user, pw = ab.creds()
    orig, rows, firefox = ab.snapshot_override(ab.OVERRIDE), [], None
    try:
        firefox = ab.open_workload()
        time.sleep(5)
        for v in variants:
            ab.OVERRIDE.write_text(json.dumps({"args": ab.VARIANTS[v]}))
            ab.restart_selkies(user, pw)
            ab.warm_up(user, pw, script="latency.mjs", extra=WARMUP_ARGS, timeout=CELL_TIMEOUT)
            for p in [p for p in profiles for _ in range(repeats)]:
                r = ab.run_one(v, p, user, pw, script="latency.mjs", timeout=CELL_TIMEOUT)
                row = latstats.flat(v, p, r)
                row["problems"] = problems(ab.VARIANTS[v], r, row)
                row["valid"] = not row["problems"]
                row |= {k: r.get(k) for k in ("codec", "fps", "foreign", "watchdog", "lost", "cuts_gt30_per5m")}
                row["raw"] = {k: r.get(k) for k in ("samples", "presentedTimes", "decodedFrames")}
                rows.append(row)
                print(json.dumps({k: v_ for k, v_ in row.items() if k != "raw"}), flush=True)
                if row["foreign"]:
                    print(f"ABORT: a user tab ({row['foreign']}) connected; yielding the seat", flush=True)
                    return
    finally:
        ab.restore_override(ab.OVERRIDE, orig)
        try:
            if firefox:
                firefox.terminate()
            ab.restart_selkies(user, pw)          # back onto the original settings
        finally:
            if rows:
                print(f"wrote {write_results(rows, ab.HERE / 'results')}\n{latstats.table(rows)}")
