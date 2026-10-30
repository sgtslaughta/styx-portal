"""Stream A/B harness: run each variant (selkies flags) under each network
profile with a headless controller, no human in the loop.

    python3 ab.py --variants h264-16,h264-30,av1-30 --profiles hotel,office

Per variant: write stream-override.json, restart only selkies (the agent
respawns it; the seat and its apps survive), open the workload page in the
seat. Per profile: netem.py in front of the gateway, run.mjs drives it, the
selkies.log slice is summarized. Results: results/<stamp>.json and .md.
Needs the seat idle: the gateway refuses a second controlling tab while
another one has input (gateway.py BUSY_CODE).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from base64 import b64encode
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "docs/spikes/2026-10-30-shallow-pipe"))
import cc_report  # noqa: E402

INSTALL = Path.home() / ".local/share/styx-agent"
LOG = INSTALL / "logs/selkies.log"
OVERRIDE = INSTALL / "stream-override.json"
CONFIG = Path.home() / ".config/styx-agent/config.json"
GATEWAY, PROXY = 8443, 18443

VARIANTS = {
    "h264-16": ["--encoder=h264enc", "--video-bitrate=16000,1000-16000"],
    "h264-30": ["--encoder=h264enc", "--video-bitrate=30000,1000-30000"],
    "av1-30": ["--encoder=av1enc,h265enc,h264enc", "--video-bitrate=30000,1000-30000"],
}
SETTINGS = re.compile(r"Stream settings active -> .*?Mode: (\S+) \((\w+)\).*?(CBR \d+|CRF: \d+)")
DECODE_FPS = re.compile(r"decoder keeps up with (\d+) fps")


def creds() -> tuple[str, str]:
    c = json.loads(CONFIG.read_text())
    return c["selkies_user"], c["selkies_password"]


def gateway_ready(user: str, pw: str) -> bool:
    req = urllib.request.Request(f"http://127.0.0.1:{GATEWAY}/")
    req.add_header("Authorization", "Basic " + b64encode(f"{user}:{pw}".encode()).decode())
    try:
        return urllib.request.urlopen(req, timeout=3).status == 200
    except OSError:
        return False


def restart_selkies(user: str, pw: str) -> None:
    """Kill selkies; the agent respawns it with the current override."""
    subprocess.run(["pkill", "-f", f"{INSTALL}/engine.py --port"], check=False)
    time.sleep(4)
    for _ in range(60):
        if gateway_ready(user, pw):
            time.sleep(3)
            return
        time.sleep(1)
    raise RuntimeError("selkies did not come back")


def seat_env() -> dict:
    env = dict(os.environ)
    env["DBUS_SESSION_BUS_ADDRESS"] = (INSTALL / "gnome-bus.addr").read_text().strip()
    env["WAYLAND_DISPLAY"] = "wayland-70"
    env.pop("DISPLAY", None)
    return env


def open_workload() -> subprocess.Popen:
    profile = HERE / "results/.firefox"
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        ["firefox", "--no-remote", "--profile", str(profile), "--kiosk", (HERE / "workload.html").as_uri()],
        env=seat_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def log_lines() -> int:
    with open(LOG, "rb") as f:
        return sum(1 for _ in f)


def server_metrics(start: int) -> dict:
    with open(LOG, errors="replace") as f:
        lines = f.readlines()[start:]
    out = cc_report.summarize(lines)
    modes = [m.groups() for line in lines if (m := SETTINGS.search(line))]
    fps = [int(m[1]) for line in lines if (m := DECODE_FPS.search(line))]
    out["codec"] = f"{modes[-1][0]} {modes[-1][1]} {modes[-1][2]}" if modes else "?"
    out["decode_fps_min"] = min(fps) if fps else None
    out["lost"] = sum("lost by a client" in line for line in lines)
    return out


def run_one(variant: str, profile: str, user: str, pw: str, refuse: str = "") -> dict:
    start = log_lines()
    proxy = subprocess.Popen([sys.executable, str(HERE / "netem.py"), f"--profile={profile}",
                              f"--listen={PROXY}", f"--target=127.0.0.1:{GATEWAY}"])
    try:
        time.sleep(1)
        args = ["node", str(HERE / "run.mjs"), f"--url=http://127.0.0.1:{PROXY}/"]
        if refuse:
            args.append(f"--refuse={refuse}")
        # Credentials via env, not argv: argv is world-readable in ps.
        env = {**os.environ, "STYX_USER": user, "STYX_PASS": pw}
        r = subprocess.run(args, capture_output=True, text=True, timeout=240, cwd=HERE.parent, env=env)
        client = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {"error": r.stderr[-400:]}
    finally:
        proxy.terminate()
    time.sleep(2)
    return {"variant": variant, "profile": profile, "refuse": refuse, **server_metrics(start), **client}


def table(rows: list) -> str:
    cols = ["variant", "profile", "refuse", "codec", "q_floor_p90", "cuts_gt30_per5m", "lost",
            "decode_fps_min", "sharpStill", "sharpAfterScroll", "sharpEnd"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(
            f"{r.get(c):.2f}" if isinstance(r.get(c), float) else str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="h264-16,h264-30,av1-30")
    ap.add_argument("--profiles", default="hotel,office")
    ap.add_argument("--fallback", action="store_true", help="also run av1-30 with AV1 refused by the browser")
    a = ap.parse_args()
    user, pw = creds()
    rows, firefox = [], open_workload()
    try:
        time.sleep(5)
        for v in a.variants.split(","):
            OVERRIDE.write_text(json.dumps({"args": VARIANTS[v]}))
            restart_selkies(user, pw)
            for p in a.profiles.split(","):
                rows.append(run_one(v, p, user, pw))
                print(json.dumps(rows[-1]), flush=True)
        if a.fallback:
            OVERRIDE.write_text(json.dumps({"args": VARIANTS["av1-30"]}))
            restart_selkies(user, pw)
            rows.append(run_one("av1-30", "lan", user, pw, refuse="av01"))
            print(json.dumps(rows[-1]), flush=True)
    finally:
        OVERRIDE.unlink(missing_ok=True)
        restart_selkies(user, pw)
        firefox.terminate()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    res = HERE / "results"
    (res / f"{stamp}.json").write_text(json.dumps(rows, indent=1))
    (res / f"{stamp}.md").write_text(table(rows) + "\n")
    print(table(rows))


if __name__ == "__main__":
    main()
