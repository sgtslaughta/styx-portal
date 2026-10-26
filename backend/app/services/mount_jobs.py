"""Managed base path: plan + apply job (spec §3.1, §3.2)."""
import asyncio
import logging
import shutil
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from docker.errors import APIError
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
    already_set: bool = False
    retry: bool = False           # settings file not there yet: the app may still be starting
    create: bool = False          # the settings file doesn't exist yet: Styx writes it from `template`
    template: str | None = None
    owner_from: str | None = None  # existing file whose uid/gid the new file copies
    manual: bool = False          # k8s: Styx can't edit the app's files; `reason` holds the instructions


def plan_mount(svc: ProxiedService, preset: ServicePreset | None, docker) -> MountPlan:
    if svc.kind != "docker-local" or not svc.container:
        return MountPlan(reason="Styx can only configure apps running as local containers.")
    methods = [m for m in ((preset.subpath or {}).get("methods", []) if preset else [])
               if m.get("type") == "config_file"]   # ponytail: env method not implemented (spec §3.1)
    if not methods:
        return MountPlan(reason="This app can't be configured by Styx. Set its base path by hand.")
    if Settings().ROUTE_BACKEND == "k8s":
        m = methods[0]
        path = m["paths"][0]
        return MountPlan("config_file", path, m["format"], m["key"], needs_consent=False, manual=True,
                         reason=f"On Kubernetes, Styx can't edit {preset.name}'s files. Set `{m['key']}` to "
                                f"`/{svc.slug}` in `{path}` and restart the app — or switch this service "
                                "to cookie-root mode, which needs no base path.")
    needs_consent = docker.container_labels(svc.container).get("styx.managed") != "true"
    new = f"/{svc.slug}"
    for m in methods:
        for path in m["paths"]:
            try:
                got = docker.read_file(svc.container, path)
            except (ValueError, APIError) as err:
                return MountPlan(needs_consent=needs_consent,
                                 reason=f"Styx couldn't read {preset.name}'s settings file: {err}")
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
                plan.already_set = True
            else:
                plan.changes = [{"target": path, "key": m["key"], "old": old, "new": new}]
            return plan
    for m in methods:
        if (c := m.get("create")) and (plan := _plan_create(m, c, new, svc, needs_consent, docker)):
            return plan
    return MountPlan(needs_consent=needs_consent, retry=True,
                     reason=f"Styx can't find {preset.name}'s settings file in the container "
                             "(settings on a tmpfs mount can't be read)."
                             + (f" {hint}" if (hint := (preset.subpath or {}).get("missing_hint")) else ""))


def _plan_create(m, c, new, svc, needs_consent, docker) -> MountPlan | None:
    """Plan writing a missing settings file; None when its owner can't be read (keep the old reason)."""
    try:
        if docker.read_file(svc.container, c["owner_from"]) is None:
            return None
        old = read_config(c["template"], m["format"], m["key"])
    except (ValueError, APIError):
        return None
    if old == new:
        return None
    change = {"target": c["path"], "key": m["key"], "old": old, "new": new, "created": True}
    return MountPlan("config_file", c["path"], m["format"], m["key"], [change], needs_consent,
                     create=True, template=c["template"], owner_from=c["owner_from"])


STEPS = [("backup", "Back up settings"), ("apply", "Apply base path"),
         ("restart", "Restart app"), ("verify", "Check the app responds")]
VERIFY_BUDGET_S = 90
VERIFY_INTERVAL_S = 2
KEEP_BACKUPS = 5
BIND_DETAIL = ("This settings file is mounted on its own, so Styx can't replace it. "
               "Mount its folder instead, or set the base path by hand.")
PROBE_DETAIL = "Styx couldn't start its check (probe image unavailable)"


def _probe_getter(docker, svc):
    hosts = {"host.docker.internal": "host-gateway"} if svc.upstream_fallback else None

    async def get(url: str) -> int:
        return await asyncio.to_thread(docker.probe_http, url, _settings.SERVICES_NETWORK,
                                       extra_hosts=hosts)
    return get


async def _verify(get, url: str) -> str:
    """"ok", "down" (no answer in budget) or "probe" (the check itself couldn't run)."""
    loop = asyncio.get_running_loop()
    end = loop.time() + VERIFY_BUDGET_S
    while True:
        code = await get(url)
        if 200 <= code < 400:
            return "ok"
        if code < 0:
            return "probe"
        if loop.time() >= end:
            return "down"
        await asyncio.sleep(VERIFY_INTERVAL_S)


class _BindMounted(Exception):
    pass


def _prune(svc_dir: Path) -> None:
    for old in sorted(p for p in svc_dir.iterdir() if p.is_dir())[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)


async def _finish_ok(session_factory, svc_id, after_done):
    """Base path confirmed: mark managed, then let the caller react (e.g. re-fetch the favicon)."""
    await _set_managed(session_factory, svc_id)
    if after_done:
        try:
            await after_done(svc_id)
        except Exception:  # noqa: BLE001 - a follow-up must never break a finished job
            logger.warning("after-done hook failed for %s", svc_id, exc_info=True)


async def _set_managed(session_factory, svc_id):
    async with session_factory() as s:
        svc = await s.get(ProxiedService, svc_id)
        svc.mount_managed = True
        s.add(svc)
        await s.commit()


async def run_job(job_id, svc_id, plan, docker, session_factory, http_get=None,
                  verify_path=None, old_verify_path=None, after_done=None) -> None:
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
        get = http_get or _probe_getter(docker, svc)
        verify_path = verify_path or f"/{svc.slug}"
        if not plan.changes:
            for i, _ in STEPS:
                mark(i, "skipped")
            await save("done", changes=[])
            await _finish_ok(session_factory, svc_id, after_done)
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
        if plan.create:
            owner = await asyncio.to_thread(docker.read_file, c, plan.owner_from)
            if owner is None:
                raise FileNotFoundError(f"{plan.owner_from} not found in the container "
                                        "(needed to copy the file owner)")
            original, info = plan.template.encode(), tarfile.TarInfo(Path(path).name)
            info.uid, info.gid, info.mode = owner[1].uid, owner[1].gid, 0o644
        else:
            got = await asyncio.to_thread(docker.read_file, c, path)
            if got is None:
                raise FileNotFoundError(f"{path} not found in the container")
            original, info = got
        svc_dir = Path(_settings.MOUNT_BACKUP_DIR) / svc_id
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bdir = svc_dir / stamp
        for n in range(2, 100):  # same-second jobs must not share (and overwrite) a backup
            if not bdir.exists():
                break
            bdir = svc_dir / f"{stamp}-{n}"
        bdir.mkdir(parents=True)
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
        await save(changed=True)
        try:
            await asyncio.to_thread(docker.write_file, c, path, new_text.encode("utf-8"), info)
        except Exception as e:  # noqa: BLE001
            if "device or resource busy" in str(e).lower():
                written = False  # a lone bind-mounted file can't be replaced; nothing changed
                await save(changed=False)
                raise _BindMounted(BIND_DETAIL) from e
            raise
        mark("apply", "done")
        mark("restart", "active")
        await save()
        await asyncio.to_thread(docker.restart_container, c)
        mark("restart", "done")
        mark("verify", "active")
        await save()
        res = await _verify(get, base + verify_path)
        if res == "ok":
            mark("verify", "done")
            await save("done")
            await _finish_ok(session_factory, svc_id, after_done)
            return
        mark("verify", "failed", PROBE_DETAIL if res == "probe"
             else f"No answer at {verify_path} after {VERIFY_BUDGET_S}s")
    except _BindMounted as e:
        fail_active(e)
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
        res = await _verify(get, base + (old_verify_path or "/"))
        ok = True  # the old file is back; whether the app answers again is a note, not a failure
        if res != "ok":
            why = (f"couldn't confirm the app answers ({PROBE_DETAIL})" if res == "probe"
                   else f"the app didn't answer at {old_verify_path or '/'} after {VERIFY_BUDGET_S}s")
            logs = f"{logs}\nRestored the old settings, but {why}.".strip()
            await save(log_excerpt=logs)
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
        where = f" (backup: {j.backup_dir})" if j.backup_dir else ""
        j.log_excerpt = ("Interrupted. The settings file may hold the new value: restore from the "
                         f"backup if the app is down{where}." if j.changed
                         else "Interrupted before Styx wrote anything. Nothing was changed.")
        j.steps = [{**s, "state": "failed"} if s.get("state") == "running" else s for s in j.steps or []]
        j.finished_at = datetime.now(timezone.utc)
        session.add(j)
    await session.commit()
    return len(rows)
