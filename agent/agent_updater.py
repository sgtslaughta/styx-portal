"""Standalone agent self-updater: runs in its own systemd user unit (stdlib only)."""
import argparse
import glob
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

GATE_TIMEOUT = 180
POLL_INTERVAL = 2
KEEP_BACKUPS = 3
api = api_bytes = None  # bound in main() from the installed portal_api


def _run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def state_path(install_dir: Path) -> Path:
    return Path(install_dir) / "update-state.json"


def write_state(install_dir: Path, s: dict) -> None:
    p = state_path(install_dir)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(s))
    os.replace(tmp, p)


def read_state(install_dir: Path) -> dict:
    try:
        return json.loads(state_path(install_dir).read_text())
    except (OSError, ValueError):
        return {}


def current_version(install_dir: Path) -> str:
    m = re.search(r'AGENT_VERSION\s*=\s*"([^"]+)"',
                  (Path(install_dir) / "styx_agent.py").read_text())
    return m.group(1) if m else ""


def deps_missing(install_dir: Path, deps: dict) -> list[str]:
    return [n for n, v in deps.items() if not glob.glob(
        f"{install_dir}/venv/lib/python*/site-packages/{n}-{v}.dist-info")]


def download(cfg: dict, manifest: dict, staging: Path) -> None:
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for f in manifest["files"]:
        data, _, _ = api_bytes(cfg, "/api/enroll/" + f["remote"])
        if len(data) != f["size"] or hashlib.sha256(data).hexdigest() != f["sha256"]:
            raise ValueError(f"sha256/size mismatch for {f['remote']}")
        dest = staging / f["local"]
        dest.write_bytes(data)
        if f["local"].endswith(".py"):
            py_compile.compile(str(dest), cfile=str(staging / ".pyc" / (f["local"] + "c")),
                               doraise=True)


def prune_backups(install_dir: Path) -> None:
    root = Path(install_dir) / "backups"
    if root.is_dir():
        for old in sorted(p for p in root.iterdir() if p.is_dir())[:-KEEP_BACKUPS]:
            shutil.rmtree(old, ignore_errors=True)


def backup(install_dir: Path, manifest: dict, from_ver: str) -> Path:
    dest = Path(install_dir) / "backups" / f"{time.strftime('%Y%m%d%H%M%S')}-{from_ver}"
    dest.mkdir(parents=True)
    for f in manifest["files"]:
        src = Path(install_dir) / f["local"]
        if src.is_file():
            shutil.copy2(src, dest / f["local"])
    prune_backups(install_dir)
    return dest


def swap(install_dir: Path, manifest: dict, staging: Path) -> None:
    for f in manifest["files"]:
        new, cur = staging / f["local"], Path(install_dir) / f["local"]
        if cur.is_file():
            shutil.copymode(cur, new)   # keep exec bits (uninstall.sh)
        os.replace(new, cur)


def restore(install_dir: Path, bdir: Path) -> None:
    for src in bdir.iterdir():
        tmp = Path(install_dir) / (src.name + ".restore")
        shutil.copy2(src, tmp)
        os.replace(tmp, Path(install_dir) / src.name)


def gate(install_dir: Path) -> bool:
    deadline = time.monotonic() + GATE_TIMEOUT
    while True:
        if read_state(install_dir).get("state") == "ok":
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_INTERVAL)


def _fail(install_dir: Path, s: dict, state: str, err: str) -> int:
    write_state(install_dir, {**s, "state": state, "error": err[:500], "at": time.time()})
    return 1


def _rolled_back(install_dir: Path, s: dict) -> int:
    tail = "\n".join(_run(["journalctl", "--user", "-u", "styx-agent", "-n", "15",
                           "--no-pager"])[1].splitlines()[-15:])
    return _fail(install_dir, s, "rolled_back",
                 "new agent not healthy in 180 s: " + tail)


def main(argv: list[str]) -> int:
    global api, api_bytes
    ap = argparse.ArgumentParser()
    ap.add_argument("--install-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--target", required=True)
    a = ap.parse_args(argv)
    inst = Path(a.install_dir)
    staging = inst / ".update-staging"
    s = {"state": "updating", "from": current_version(inst), "to": a.target,
         "error": None, "at": time.time()}
    write_state(inst, s)
    try:
        sys.path.insert(0, str(inst))
        if api is None:
            from portal_api import api as _api, api_bytes as _ab
            api, api_bytes = _api, _ab
        cfg = json.loads(Path(a.config).read_text())
        m = api(cfg, "/api/agent/update-manifest")
        if m["version"] != a.target:
            return _fail(inst, s, "failed", f"manifest version {m['version']} != {a.target}")
        if deps_missing(inst, m.get("deps", {})):
            return _full(inst, cfg, s, staging)
        download(cfg, m, staging)
        bdir = backup(inst, m, s["from"])
    except Exception as e:  # nothing swapped yet
        shutil.rmtree(staging, ignore_errors=True)
        return _fail(inst, s, "failed", f"{type(e).__name__}: {e}")
    swap(inst, m, staging)
    shutil.rmtree(staging, ignore_errors=True)
    _run(["systemctl", "--user", "restart", "styx-agent"])
    if gate(inst):
        return 0
    restore(inst, bdir)
    _run(["systemctl", "--user", "restart", "styx-agent"])
    return _rolled_back(inst, s)


def _full(inst: Path, cfg: dict, s: dict, staging: Path) -> int:
    try:
        from health import rollback  # old copy, imported before the swap
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        script = staging / "enroll.sh"
        script.write_bytes(api_bytes(cfg, "/api/enroll/script")[0])
        script_copy = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "styx-enroll.sh"
        shutil.copyfile(script, script_copy)  # staging lives inside the dir being replaced
        rc, out = _run(["bash", str(script_copy), "--upgrade", "--server", cfg["server"]])
    except Exception as e:
        return _fail(inst, s, "failed", f"{type(e).__name__}: {e}")
    if rc != 0:
        return _fail(inst, s, "failed", f"enroll --upgrade exited {rc}: {out[-300:]}")
    write_state(inst, s)  # new install dir starts without the state file
    if gate(inst):
        return 0
    rollback(inst)
    return _rolled_back(inst, s)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
