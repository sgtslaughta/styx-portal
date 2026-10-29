"""Pre-pull instance images on every node via a DaemonSet of pull-only initContainers."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlmodel import select

from app.config import Settings
from app.models import ServiceTemplate
from app.services.k8s_instance_objects import MANAGED, refuse_reason

logger = logging.getLogger("styx-portal")
NAME = "styx-image-prepull"
_RES = {"requests": {"cpu": "1m", "memory": "8Mi"}}
_SEC = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}
_bg: set[asyncio.Task] = set()


def build_prepull_daemonset(images: list[str], ns: str, stamp: str | None = None) -> dict:
    stamp = stamp or datetime.now(timezone.utc).isoformat()
    labels = {"app": NAME, **MANAGED}
    # ponytail: images whose shell lacks sh fail the initContainer; add a per-template pull-only flag if that happens
    inits = [{"name": f"img-{i}", "image": img, "imagePullPolicy": "Always",
              "command": ["sh", "-c", "exit 0"], "resources": _RES,
              "securityContext": dict(_SEC)} for i, img in enumerate(images)]
    pod = {"automountServiceAccountToken": False, "enableServiceLinks": False,
           "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
           "tolerations": [{"operator": "Exists"}], "initContainers": inits,
           "containers": [{"name": "pause", "image": "registry.k8s.io/pause:3.10",
                           "resources": _RES, "securityContext": dict(_SEC)}]}
    return {"apiVersion": "apps/v1", "kind": "DaemonSet",
            "metadata": {"name": NAME, "namespace": ns, "labels": dict(MANAGED)},
            "spec": {"selector": {"matchLabels": {"app": NAME}},
                     "template": {"metadata": {"labels": labels,
                                               "annotations": {"styx/prepull-at": stamp}},
                                  "spec": pod}}}


def prepull_images(templates) -> list[str]:
    out: list[str] = []
    for t in templates:
        if refuse_reason(t):
            continue
        img = t.image if "/" in t.image else Settings().K8S_DESKTOP_IMAGE
        if img not in out:
            out.append(img)
    return out


async def sync_prepull(session) -> None:
    if Settings().ROUTE_BACKEND != "k8s":
        return
    from app.services.k8s_api import incluster_client
    templates = (await session.exec(select(ServiceTemplate))).all()
    ds = build_prepull_daemonset(prepull_images(templates), Settings().K8S_INSTANCE_NAMESPACE)
    await asyncio.to_thread(incluster_client().apply, ds)


async def _sync_own_session() -> None:
    from app.database import async_session
    try:
        async with async_session() as session:
            await sync_prepull(session)
    except Exception:  # noqa: BLE001 - best effort
        logger.warning("image prepull sync failed", exc_info=True)


def schedule_sync() -> None:
    """Fire-and-forget sync (after template changes); no-op off k8s."""
    if Settings().ROUTE_BACKEND != "k8s":
        return
    t = asyncio.create_task(_sync_own_session())
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def prepull_loop(hour: int = 3) -> None:
    """Sync at startup, then nightly at `hour` local time (bumps the annotation => re-pull)."""
    last_day = None
    await _sync_own_session()
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        if now.hour == hour and last_day != now.date():
            last_day = now.date()
            await _sync_own_session()
