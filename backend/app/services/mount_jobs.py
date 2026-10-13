"""Managed base path: plan + apply job (spec §3.1, §3.2)."""
import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlmodel import select

from app.config import Settings
from app.models import MountJob, ProxiedService, ServicePreset, upstream_base
from app.services.mount_edit import edit_config, read_config

_settings = Settings()
logger = logging.getLogger("styx-portal")


@dataclass
class MountPlan:
    method: str | None = None
    path: str | None = None
    fmt: str | None = None
    key: str | None = None
    changes: list[dict] = field(default_factory=list)
    needs_consent: bool = True
    reason: str | None = None


def plan_mount(svc: ProxiedService, preset: ServicePreset | None, docker) -> MountPlan:
    if svc.kind != "docker-local" or not svc.container:
        return MountPlan(reason="Styx can only configure apps running as local containers.")
    methods = [m for m in ((preset.subpath or {}).get("methods", []) if preset else [])
               if m.get("type") == "config_file"]   # ponytail: env method not implemented (spec §3.1)
    if not methods:
        return MountPlan(reason="This app can't be configured by Styx. Set its base path by hand.")
    needs_consent = docker.container_labels(svc.container).get("styx.managed") != "true"
    new = f"/{svc.slug}"
    for m in methods:
        for path in m["paths"]:
            got = docker.read_file(svc.container, path)
            if got is None:
                continue
            try:
                old = read_config(got[0].decode("utf-8"), m["format"], m["key"])
            except ValueError as err:  # UnicodeDecodeError is a ValueError
                return MountPlan(needs_consent=needs_consent,
                                 reason=f"Styx couldn't read {preset.name}'s settings file: {err}")
            plan = MountPlan("config_file", path, m["format"], m["key"], [], needs_consent)
            if old == new:
                plan.reason = f"Base path is already {new}."
            else:
                plan.changes = [{"target": path, "key": m["key"], "old": old, "new": new}]
            return plan
    return MountPlan(needs_consent=needs_consent,
                     reason=f"Styx can't find {preset.name}'s settings file in the container.")


STEPS = [("backup", "Back up settings"), ("apply", "Apply base path"),
         ("restart", "Restart app"), ("verify", "Check it answers")]
VERIFY_BUDGET_S = 90
VERIFY_INTERVAL_S = 2
KEEP_BACKUPS = 5


async def _default_get(url: str) -> int:
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as c:
        try:
            return (await c.get(url)).status_code
        except httpx.HTTPError:
            return 0


async def _verify(get, url: str) -> bool:
    loop = asyncio.get_running_loop()
    end = loop.time() + VERIFY_BUDGET_S
    while True:
        if 200 <= await get(url) < 400:
            return True
        if loop.time() >= end:
            return False
        await asyncio.sleep(VERIFY_INTERVAL_S)


def _prune(svc_dir: Path) -> None:
    for old in sorted(p for p in svc_dir.iterdir() if p.is_dir())[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)


async def _set_managed(session_factory, svc_id):
    async with session_factory() as s:
        svc = await s.get(ProxiedService, svc_id)
        svc.mount_managed = True
        s.add(svc)
        await s.commit()


async def run_job(job_id, svc_id, plan, docker, session_factory, http_get=None,
                  verify_path=None, old_verify_path=None) -> None:
    get = http_get or _default_get
    steps = [{"id": i, "label": label, "state": "pending", "detail": None} for i, label in STEPS]

    async def save(state=None, **kw):
        async with session_factory() as s:
            job = await s.get(MountJob, job_id)
            job.steps = [dict(x) for x in steps]
            if state:
                job.state = state
            for k, v in kw.items():
                setattr(job, k, v)
            if state in ("done", "rolled_back", "failed"):
                job.finished_at = datetime.now(timezone.utc)
            s.add(job)
            await s.commit()

    def mark(step_id, state, detail=None):
        for x in steps:
            if x["id"] == step_id:
                x["state"], x["detail"] = state, detail

    def fail_active(err):
        for x in steps:
            if x["state"] == "active":
                x["state"], x["detail"] = "failed", str(err)

    try:
        async with session_factory() as s:
            svc = await s.get(ProxiedService, svc_id)
        base = upstream_base(svc)
        verify_path = verify_path or f"/{svc.slug}"
        if not plan.changes:
            for i, _ in STEPS:
                mark(i, "skipped")
            await save("done", changes=[])
            await _set_managed(session_factory, svc_id)
            return
        await save("running", changes=plan.changes)
    except Exception as e:  # noqa: BLE001 - never leave the job pending
        logger.exception("mount job %s pre-flight failed", job_id)
        steps[0]["state"], steps[0]["detail"] = "failed", str(e)
        await save("failed")
        return
    c, path = svc.container, plan.path
    bdir = None
    mark("backup", "active")
    try:
        await save()
        got = await asyncio.to_thread(docker.read_file, c, path)
        if got is None:
            raise FileNotFoundError(f"{path} not found in the container")
        original, info = got
        svc_dir = Path(_settings.MOUNT_BACKUP_DIR) / svc_id
        bdir = svc_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / Path(path).name).write_bytes(original)
        _prune(svc_dir)
    except Exception as e:  # noqa: BLE001 - nothing changed yet, just fail the job
        fail_active(e)
        await save("failed", backup_dir=str(bdir) if bdir else None)
        return
    mark("backup", "done", str(bdir))
    mark("apply", "active")
    await save(backup_dir=str(bdir))
    written = False
    try:
        new_text, _ = edit_config(original.decode("utf-8"), plan.fmt, plan.key, plan.changes[0]["new"])
        written = True  # from here on a failed write may have partly landed
        await asyncio.to_thread(docker.write_file, c, path, new_text.encode("utf-8"), info)
        mark("apply", "done")
        mark("restart", "active")
        await save()
        await asyncio.to_thread(docker.restart_container, c)
        mark("restart", "done")
        mark("verify", "active")
        await save()
        if await _verify(get, base + verify_path):
            mark("verify", "done")
            await save("done")
            await _set_managed(session_factory, svc_id)
            return
        mark("verify", "failed", f"No answer at {verify_path} after {VERIFY_BUDGET_S}s")
    except Exception as e:  # noqa: BLE001 - any failure triggers rollback
        fail_active(e)
    if not written:
        await save("failed")
        return
    try:
        logs = await asyncio.to_thread(docker.container_logs, c, 20)
    except Exception:  # noqa: BLE001 - logs are best effort, rollback is not
        logs = ""
    await save(log_excerpt=logs)
    try:
        await asyncio.to_thread(docker.write_file, c, path, original, info)
        await asyncio.to_thread(docker.restart_container, c)
        ok = await _verify(get, base + (old_verify_path or "/"))
    except Exception as e:  # noqa: BLE001
        logger.exception("mount job %s rollback failed", job_id)
        logs = f"{logs}\nRollback failed: {e}. Backup at {bdir}".strip()
        await save(log_excerpt=logs)
        ok = False
    await save("rolled_back" if ok else "failed")


async def sweep_interrupted(session) -> int:
    rows = (await session.exec(select(MountJob).where(MountJob.state.in_(["pending", "running"])))).all()
    for j in rows:
        j.state = "failed"
        j.log_excerpt = f"Interrupted - backup kept at {j.backup_dir}"
        j.finished_at = datetime.now(timezone.utc)
        session.add(j)
    await session.commit()
    return len(rows)
