"""Pre-pull instance images on every node via a DaemonSet of pull-only initContainers."""
import asyncio
import hashlib
import logging
from datetime import datetime, timezone

from sqlmodel import select

from app.config import Settings
from app.models import ServiceTemplate, User
from app.services.k8s_instance_objects import MANAGED, refuse_reason

logger = logging.getLogger("styx-portal")
PREFIX = "styx-prepull-"
_RES = {"requests": {"cpu": "10m", "memory": "16Mi"}, "limits": {"cpu": "10m", "memory": "16Mi"}}
_SEC = {"runAsNonRoot": True, "runAsUser": 65534, "runAsGroup": 65534,
        "allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]}}
_bg: set[asyncio.Task] = set()


def prepull_name(image: str) -> str:
    return PREFIX + hashlib.sha1(image.encode(), usedforsecurity=False).hexdigest()[:10]


def build_prepull_daemonset(image: str, ns: str, stamp: str | None = None) -> dict:
    stamp = stamp or datetime.now(timezone.utc).isoformat()
    name = prepull_name(image)
    labels = {"app": name, "styx/prepull": "true", **MANAGED}
    # ponytail: images whose shell lacks sh (or can't run as 65534) fail the initContainer; add a per-template pull-only flag if that happens
    init = {"name": "img", "image": image, "imagePullPolicy": "Always",
            "command": ["sh", "-c", "exit 0"], "resources": _RES, "securityContext": dict(_SEC)}
    pod = {"automountServiceAccountToken": False, "enableServiceLinks": False,
           "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
           "initContainers": [init],
           "containers": [{"name": "pause", "image": "registry.k8s.io/pause:3.10",
                           "resources": _RES, "securityContext": dict(_SEC)}]}
    return {"apiVersion": "apps/v1", "kind": "DaemonSet",
            "metadata": {"name": name, "namespace": ns,
                         "labels": {"styx/prepull": "true", **MANAGED}},
            "spec": {"selector": {"matchLabels": {"app": name}},
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
    # only shared or admin-owned templates: member templates pull at launch
    rows = await session.exec(
        select(ServiceTemplate).outerjoin(User, ServiceTemplate.owner_id == User.id)
        .where((ServiceTemplate.owner_id.is_(None)) | (User.role == "admin")))
    ns = Settings().K8S_INSTANCE_NAMESPACE
    desired = {prepull_name(i): i for i in prepull_images(rows.all())}
    client = incluster_client()

    def _apply() -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        for img in desired.values():
            client.apply(build_prepull_daemonset(img, ns, stamp))
        for name in client.list_names("apps/v1", "DaemonSet", ns, "styx/prepull=true"):
            if name not in desired:
                client.delete("apps/v1", "DaemonSet", ns, name)
    await asyncio.to_thread(_apply)


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
