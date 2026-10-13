"""Managed base path endpoints (spec 3.2, 9). Admin only."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import async_session, get_session
from app.models import MountJob, ServicePreset, User
from app.routers.services import _get_or_404, _iso, get_docker_manager
from app.security.deps import require_admin
from app.services.audit import audit_request
from app.services.docker_manager import DockerManager
from app.services.mount_jobs import plan_mount, run_job

logger = logging.getLogger("styx-portal")
router = APIRouter()
_tasks: set[asyncio.Task] = set()


class ApplyBody(BaseModel):
    consent: bool = False


def _log_failure(t: asyncio.Task) -> None:
    if not t.cancelled() and t.exception():
        logger.error("mount job crashed", exc_info=t.exception())


def _start(*args, **kw) -> None:
    t = asyncio.create_task(run_job(*args, **kw))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    t.add_done_callback(_log_failure)


async def _plan(session, sid, docker):
    svc = await _get_or_404(session, sid)
    preset = await session.get(ServicePreset, svc.preset_id) if svc.preset_id else None
    return svc, preset, await asyncio.to_thread(plan_mount, svc, preset, docker)


@router.post("/{sid}/mount/plan")
async def mount_plan(sid: str, admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session),
                     docker: DockerManager = Depends(get_docker_manager)):
    _, _, p = await _plan(session, sid, docker)
    return {"method": p.method, "changes": p.changes, "needs_consent": p.needs_consent,
            "reason": p.reason}


@router.post("/{sid}/mount/apply", status_code=202)
async def mount_apply(sid: str, body: ApplyBody, request: Request,
                      admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session),
                      docker: DockerManager = Depends(get_docker_manager)):
    running = (await session.exec(select(MountJob).where(
        MountJob.service_id == sid, MountJob.state.in_(["pending", "running"])))).first()
    if running:
        raise HTTPException(409, "A change is already running for this service")
    svc, preset, p = await _plan(session, sid, docker)
    if p.method is None or not p.path:
        raise HTTPException(409, p.reason or "Nothing to apply")
    if p.needs_consent and not body.consent:
        raise HTTPException(409, "This container wasn't created by Styx. Confirm the change first.")
    verify = ((preset.subpath or {}).get("verify_path") or "/{slug}").format(slug=svc.slug)
    old = (preset.health_path or "/").removeprefix(f"/{svc.slug}") or "/"
    job = MountJob(service_id=sid, changes=p.changes)
    session.add(job)
    await audit_request(session, request, "service.mount_apply", user_id=admin.id,
                        resource=sid,
                        detail={"service": svc.slug, "changes": p.changes, "consent": body.consent})
    await session.commit()
    _start(job.id, sid, p, docker, async_session, verify_path=verify, old_verify_path=old)
    return {"job_id": job.id}


@router.get("/{sid}/mount/jobs/latest")
async def mount_latest(sid: str, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    job = (await session.exec(select(MountJob).where(MountJob.service_id == sid)
                              .order_by(MountJob.created_at.desc()))).first()
    if job is None:
        raise HTTPException(404, "No changes yet")
    return {"id": job.id, "state": job.state, "steps": job.steps, "changes": job.changes,
            "backup_dir": job.backup_dir, "log_excerpt": job.log_excerpt,
            "created_at": _iso(job.created_at), "finished_at": _iso(job.finished_at)}
