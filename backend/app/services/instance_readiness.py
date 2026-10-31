"""Wait for a k8s instance to become ready before marking it running."""
import asyncio
import logging
import time
from datetime import datetime, timezone

from app.database import async_session
from app.models import Instance
from app.services.k8s_runtime import instance_runtime

logger = logging.getLogger("styx-portal")

FATAL = {"ErrImagePull", "ImagePullBackOff", "CrashLoopBackOff",
         "CreateContainerConfigError", "InvalidImageName"}
FATAL_GRACE = 60
TEXT = {"Scheduling": "Waiting for a node", "ContainerCreating": "Preparing (pulling image)",
        "Starting": "Starting desktop"}
_tasks: set[asyncio.Task] = set()


async def _refresh_routes(session) -> None:
    from app.services.route_writer import refresh_routes_from_db
    await refresh_routes_from_db(session)


async def _fail(session, inst: Instance, msg: str) -> None:
    inst.status = "error"
    inst.error_message = msg
    inst.status_detail = None
    session.add(inst)
    await session.commit()


async def wait_until_ready(instance_id: str, timeout: float = 600, interval: float = 2) -> None:
    runtime = instance_runtime()
    deadline = time.monotonic() + timeout
    fatal_since: float | None = None
    async with async_session() as session:
        while True:
            inst = await session.get(Instance, instance_id)
            if inst is not None:
                await session.refresh(inst)
            if inst is None or inst.status != "starting" or not inst.container_id:
                return
            try:
                st = await asyncio.to_thread(runtime.get_container_status, inst.container_id)
            except Exception:  # noqa: BLE001 - transient API error, retry
                logger.warning("readiness check failed for %s", instance_id, exc_info=True)
                st = {"status": "created", "detail": "Starting"}
            if st["status"] == "running":
                now = datetime.now(timezone.utc)
                inst.status = "running"
                inst.started_at = now
                inst.last_activity = now
                inst.status_detail = None
                session.add(inst)
                await session.commit()
                await _refresh_routes(session)
                return
            detail = st.get("detail") or "Starting"
            if detail in FATAL:
                fatal_since = fatal_since or time.monotonic()
                if time.monotonic() - fatal_since > FATAL_GRACE:
                    await _fail(session, inst, f"Instance failed to start: {detail}")
                    return
            else:
                fatal_since = None
            if time.monotonic() > deadline:
                await _fail(session, inst, "Instance did not become ready in time")
                return
            text = TEXT.get(detail, detail)
            if inst.status_detail != text:
                inst.status_detail = text
                session.add(inst)
                await session.commit()
            await asyncio.sleep(interval)


def start_waiting(instance_id: str) -> None:
    task = asyncio.create_task(wait_until_ready(instance_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def defer_on_k8s(instance: Instance) -> None:
    """On k8s a scaled-up Deployment is not up yet: park the instance in 'starting'."""
    from app.config import Settings
    if Settings().ROUTE_BACKEND == "k8s":
        instance.status = "starting"
        instance.status_detail = "Starting"


def kick(instance: Instance) -> None:
    """After commit: start the readiness waiter if the instance was deferred."""
    if instance.status == "starting":
        start_waiting(instance.id)
