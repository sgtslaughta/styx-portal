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
import signal
import subprocess
import sys
import time
import urllib.request
from base64 import b64encode
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "docs/spikes/2026-10-30-shallow-pipe"))
import cc_report  # noqa: E402
import probes  # noqa: E402

INSTALL = Path.home() / ".local/share/styx-agent"
LOG = INSTALL / "logs/selkies.log"
OVERRIDE = INSTALL / "stream-override.json"
CONFIG = Path.home() / ".config/styx-agent/config.json"
GATEWAY, PROXY = 8443, 18443

VARIANTS = {
    "h264-16": ["--encoder=h264enc", "--video-bitrate=16000,1000-16000"],
    "h264-30": ["--encoder=h264enc", "--video-bitrate=30000,1000-30000"],
    "av1-30": ["--encoder=av1enc,h265enc,h264enc", "--video-bitrate=30000,1000-30000"],
    "av1-16": ["--encoder=av1enc,h265enc,h264enc", "--video-bitrate=16000,1000-16000"],
}
GWLOG = INSTALL / "logs/gateway.log"
WS_OPEN = re.compile(r"ws open .*from=(\S+)")


def watchdog_restarts(lines) -> int:
    """Agent watchdog restarts of selkies (15 s with no frame while driven):
    a run that had one measured a restart, not the variant."""
    return sum("watchdog: viewer frameless" in line for line in lines)


def journal_since(since: str) -> list:
    r = subprocess.run(["journalctl", "--user", "-u", "styx-agent", "--since", since, "--no-pager"],
                       capture_output=True, text=True, check=False)
    return r.stdout.splitlines()


MIN_MOTION_FPS = 10      # an outage run measures nothing without steady motion


def motion_ok(profile: str, client: dict) -> bool:
    """An outage (drop*) run counts only if its animation actually streamed."""
    if not profile.startswith("drop"):
        return True
    marks = dict(client.get("marks") or [])
    span = marks.get("end", 0) - marks.get("page", 0)
    return span > 0 and (client.get("frames") or 0) >= MIN_MOTION_FPS * span


def foreign_client(lines) -> str | None:
    """A real user's tab that opened during a run: the run is void, and the
    harness yields (it would fight the user for control otherwise)."""
    for line in lines:
        if (m := WS_OPEN.search(line)) and m[1] not in ("127.0.0.1", "::1"):
            return m[1]
    return None
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


FIREFOX_PREFS = {
    "browser.aboutwelcome.enabled": "false",
    "browser.preonboarding.enabled": "false",
    "trailhead.firstrun.didSeeAboutWelcome": "true",
    "datareporting.policy.dataSubmissionEnabled": "false",
    "datareporting.policy.dataSubmissionPolicyBypassNotification": "true",
    "termsofuse.bypassNotification": "true",
    "browser.startup.homepage_override.mstone": '"ignore"',
    "browser.shell.checkDefaultBrowser": "false",
    "browser.sessionstore.resume_from_crash": "false",
}


def open_workload() -> subprocess.Popen:
    profile = HERE / "results/.firefox"
    profile.mkdir(parents=True, exist_ok=True)
    # A first-run welcome / terms dialog would cover the page and eat the input.
    (profile / "user.js").write_text("".join(f'user_pref("{k}", {v});\n' for k, v in FIREFOX_PREFS.items()))
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


def warm_up(user: str, pw: str) -> None:
    """A throwaway run after a selkies restart: the first session on a fresh
    selkies sometimes went 15 s frameless and tripped the agent watchdog
    (5 of 5 such stalls on 2026-10-30), which measured the restart, not the variant."""
    print(json.dumps({"warmup": run_one("warmup", "lan", user, pw).get("valid")}), flush=True)


def run_one(variant: str, profile: str, user: str, pw: str, refuse: str = "") -> dict:
    start, gw_start = log_lines(), GWLOG.stat().st_size
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    proxy = subprocess.Popen([sys.executable, str(HERE / "netem.py"), f"--profile={profile}",
                              f"--listen={PROXY}", f"--target=127.0.0.1:{GATEWAY}"])
    try:
        time.sleep(1)
        args = ["node", str(HERE / "run.mjs"), f"--url=http://127.0.0.1:{PROXY}/"]
        if profile.startswith("drop"):          # outage profiles: steady motion through the hole
            args.append("--mode=recovery")
        if refuse:
            args.append(f"--refuse={refuse}")
        # Credentials via env, not argv: argv is world-readable in ps.
        env = {**os.environ, "STYX_USER": user, "STYX_PASS": pw}
        sampler = probes.Sampler()
        sampler.start()
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=240, cwd=HERE.parent, env=env)
        finally:
            load = sampler.stop()
        client = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {"error": r.stderr[-400:]}
    finally:
        proxy.terminate()
    time.sleep(2)
    with open(GWLOG, errors="replace") as f:
        f.seek(gw_start)
        foreign = foreign_client(f.readlines())
    restarts = watchdog_restarts(journal_since(since))
    return {"variant": variant, "profile": profile, "refuse": refuse, "foreign": foreign,
            "watchdog": restarts, "valid": not foreign and not restarts and motion_ok(profile, client),
            **load,
            **server_metrics(start), **client}


def table(rows: list) -> str:
    cols = ["variant", "profile", "refuse", "valid", "watchdog", "foreign", "codec",
            "cuts_gt30_per5m", "lost", "latP50", "latP95", "maxGapMs", "sharpStill",
            "sharpAfterScroll", "sharpEnd", "cpu_mean", "vcn_mean", "rss_mb_growth"]
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
    ap.add_argument("--repeats", type=int, default=1)
    a = ap.parse_args()
    # systemctl stop sends SIGTERM: exit through `finally` so the override is removed.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    user, pw = creds()
    rows, firefox = [], open_workload()
    try:
        time.sleep(5)
        for v in a.variants.split(","):
            OVERRIDE.write_text(json.dumps({"args": VARIANTS[v]}))
            restart_selkies(user, pw)
            warm_up(user, pw)
            for p in [p for p in a.profiles.split(",") for _ in range(a.repeats)]:
                rows.append(run_one(v, p, user, pw))
                print(json.dumps(rows[-1]), flush=True)
                if rows[-1]["foreign"]:
                    print(f"ABORT: a user tab ({rows[-1]['foreign']}) connected; yielding the seat", flush=True)
                    return finish(rows)
        if a.fallback:
            OVERRIDE.write_text(json.dumps({"args": VARIANTS["av1-30"]}))
            restart_selkies(user, pw)
            warm_up(user, pw)
            rows.append(run_one("av1-30", "lan", user, pw, refuse="av01"))
            print(json.dumps(rows[-1]), flush=True)
    finally:
        OVERRIDE.unlink(missing_ok=True)
        restart_selkies(user, pw)
        firefox.terminate()
    finish(rows)


def finish(rows: list) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    res = HERE / "results"
    (res / f"{stamp}.json").write_text(json.dumps(rows, indent=1))
    (res / f"{stamp}.md").write_text(table(rows) + "\n")
    print(table(rows))


if __name__ == "__main__":
    main()
