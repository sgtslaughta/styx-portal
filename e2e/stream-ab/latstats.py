"""Pure stats for the gaming latency suite: latency.mjs prints raw per-sample
arrays; everything derived (percentiles, jitter, stalls, pacing, the table) is here."""
import math

KINDS = ("key", "mouse", "motion")
OVER_MS = 100            # a sample slower than this is a visible hiccup
STALL_MS = 50            # gap between presented frames, while motion is expected


def pct(vals: list, p: float) -> float | None:
    """Linear-interpolated percentile (p in 0..100) of unsorted vals."""
    if not vals:
        return None
    v = sorted(vals)
    k = (len(v) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def std(vals: list) -> float | None:
    """Population standard deviation (the jitter figure)."""
    if not vals:
        return None
    m = sum(vals) / len(vals)
    return math.sqrt(sum((x - m) ** 2 for x in vals) / len(vals))


def summarize(vals: list) -> dict:
    return {"n": len(vals), "p50": pct(vals, 50), "p95": pct(vals, 95), "p99": pct(vals, 99),
            "max": max(vals) if vals else None, "std": std(vals),
            "over100": sum(x > OVER_MS for x in vals)}


def pacing(times: list) -> dict:
    """Frame-pacing stats from presented-frame timestamps (ms) of a continuous-motion phase."""
    gaps = [b - a for a, b in zip(times, times[1:])]
    span = (times[-1] - times[0]) / 1000 if len(times) > 1 else 0
    return {"frames": len(times), "fps": len(gaps) / span if span else None,
            "interval_std": std(gaps), "interval_max": max(gaps) if gaps else None,
            "stalls": sum(g > STALL_MS for g in gaps)}


def sample_ms(s: dict, field: str) -> float | None:
    """Latency of one raw sample: field time minus the input dispatch time t0 (all performance.now())."""
    t, t0 = s.get(field), s.get("t0")
    return t - t0 if t is not None and t0 is not None and t >= t0 else None


def analyse(client: dict) -> dict:
    """Raw latency.mjs output -> {"<kind>": {"decoded": summary, "presented": summary, "missed": n}, "pacing": {...}}.
    Each kind keeps the old "decoded" metric next to the new "presented" one."""
    out = {}
    for kind in KINDS:
        raw = (client.get("samples") or {}).get(kind) or []
        dec = [v for s in raw if (v := sample_ms(s, "dec")) is not None]
        pres = [v for s in raw if (v := sample_ms(s, "pres")) is not None]
        sent = (client.get("sent") or {}).get(kind)
        out[kind] = {"decoded": summarize(dec), "presented": summarize(pres), "missed": len(raw) - len(pres),
                     "miss_rate": (len(raw) - len(pres)) / len(raw) if raw else None,
                     "sent": sent, "delivered": (client.get("delivered") or {}).get(kind)}
    out["pacing"] = pacing(client.get("presentedTimes") or [])
    return out


def flat(variant: str, profile: str, client: dict) -> dict:
    """One table cell: presented stats for each input kind plus pacing, and the legacy decoded key p50/p95."""
    a = analyse(client)
    row = {"variant": variant, "profile": profile, "sink": client.get("sink"), "error": client.get("error")}
    for k in KINDS:
        row[k] = a[k]["presented"] | {x: a[k][x] for x in ("missed", "miss_rate", "sent", "delivered")}
    row["legacy"] = {"latP50": a["key"]["decoded"]["p50"], "latP95": a["key"]["decoded"]["p95"]}
    row["pacing"] = a["pacing"]
    return row


def _f(v) -> str:
    return "-" if v is None else f"{v:.1f}" if isinstance(v, float) else str(v)


COLS = ["variant", "profile", "input", "p50", "p95", "p99", "jitter", ">100ms", "miss%", "deliv/sent", "stalls", "pacing sd", "valid"]


def table(rows: list) -> str:
    """Markdown: one line per variant x profile x input; stalls and pacing come from the motion phase."""
    out = ["| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
    for r in rows:
        pc = r.get("pacing") or {}
        for k in KINDS:
            c = r.get(k) or {}
            out.append("| " + " | ".join(_f(x) for x in (
                r["variant"], r["profile"], k, c.get("p50"), c.get("p95"), c.get("p99"), c.get("std"),
                c.get("over100"), None if c.get("miss_rate") is None else round(100 * c["miss_rate"]),
                f"{c.get('delivered')}/{c.get('sent')}", pc.get("stalls"), pc.get("interval_std"),
                r.get("valid"))) + " |")
    return "\n".join(out)
