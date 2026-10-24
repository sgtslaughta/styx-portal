"""Stand-in for the styx agent's seat refit loop, isolated from the live seat.

Xvfb :150 + selkies (active + warm standby) + agent/gateway.py on :8445.
On <seat>/refit-request: write seat-size, promote standby (selkies-port),
kill the old selkies, boot a new standby, clear the request — same order as
styx_agent. Usage: fake_agent.py <venv> <gateway_py> <seat_dir>
"""
import os
import signal
import socket
import subprocess
import sys
import time

venv, gateway_py, seat = sys.argv[1:4]
os.makedirs(seat, exist_ok=True)
log = open(os.path.join(seat, "agent.log"), "a", buffering=1)
DISPLAY = ":150"


def say(m):
    log.write(f"{time.time():.3f} {m}\n")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def selkies(port):
    env = dict(os.environ, DISPLAY=DISPLAY)
    out = open(os.path.join(seat, f"selkies-{port}.log"), "w")
    p = subprocess.Popen([f"{venv}/bin/selkies", f"--port={port}", "--enable-basic-auth=false",
                          "--mode=websockets", "--encoder=x264enc", "--framerate=30",
                          "--second-screen=false", "--audio-enabled=false|locked"],
                         env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(300):        # wait until it listens
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            say(f"selkies up port={port} pid={p.pid}")
            return p
        except OSError:
            time.sleep(0.1)
    raise SystemExit(f"selkies on {port} never listened")


def write(name, text):
    tmp = os.path.join(seat, name + ".tmp")
    open(tmp, "w").write(text)
    os.replace(tmp, os.path.join(seat, name))


procs = [subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", "3840x2160x24", "-nolisten", "tcp"])]
time.sleep(1)
# something that repaints every second so frames keep flowing
procs.append(subprocess.Popen(["python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "repaint.py")],
                              env=dict(os.environ, DISPLAY=DISPLAY)))
pa, pb = free_port(), free_port()
active, standby = (pa, selkies(pa)), (pb, selkies(pb))
write("selkies-port", str(pa))
write("seat-size", "1280x720")
gw_env = dict(os.environ, STYX_GW_USER="u", STYX_GW_PASSWORD="p", STYX_GW_SEAT_DIR=seat,
              STYX_GW_STATE=os.path.join(seat, "gw_state.json"),
              STYX_GW_ICON_DIR=os.path.dirname(gateway_py))
gw = subprocess.Popen([f"{venv}/bin/python", gateway_py, "8445", str(pa)], env=gw_env,
                      stdout=open(os.path.join(seat, "gateway.out"), "w"), stderr=subprocess.STDOUT)
procs.append(gw)
say("ready")


def stop(*_):
    for p in [active[1], standby[1], *procs]:
        try:
            os.killpg(p.pid, signal.SIGKILL) if p in (active[1], standby[1]) else p.kill()
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
req = os.path.join(seat, "refit-request")
while True:
    if os.path.exists(req):
        target = open(req).read().strip()
        say(f"refit request {target}")
        write("seat-size", target)
        old, active = active, standby
        write("selkies-port", str(active[0]))
        say(f"promoted standby port={active[0]}")
        os.killpg(old[1].pid, signal.SIGKILL)
        os.remove(req)
        say("request cleared")
        np = free_port()
        standby = (np, selkies(np))
    time.sleep(0.05)
