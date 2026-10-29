from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import Instance, ServiceTemplate
from app.services import instance_readiness as ir


class Ctx:
    def __init__(self, s):
        self.s = s

    async def __aenter__(self):
        return self.s

    async def __aexit__(self, *a):
        return False


async def _inst(session, status="starting"):
    t = ServiceTemplate(name="t", display_name="T", image="img", internal_port=3000)
    session.add(t)
    await session.commit()
    i = Instance(template_id=t.id, name="n", subdomain="sub", container_id="c", status=status)
    session.add(i)
    await session.commit()
    return i


def _run(session, statuses):
    rt = MagicMock()
    rt.get_container_status.side_effect = statuses
    return (patch.object(ir, "async_session", lambda: Ctx(session)),
            patch.object(ir, "instance_runtime", return_value=rt),
            patch.object(ir, "_refresh_routes", AsyncMock()))


async def _wait(session, statuses, **kw):
    a, b, c = _run(session, statuses)
    with a, b, c as refresh:
        await ir.wait_until_ready("x" if kw.pop("missing", False) else kw.pop("iid"), interval=0, **kw)
    return refresh


@pytest.mark.asyncio
async def test_running_sets_running(session):
    i = await _inst(session)
    refresh = await _wait(session, [{"status": "created", "detail": "ContainerCreating"},
                                    {"status": "running"}], iid=i.id)
    await session.refresh(i)
    assert i.status == "running" and i.status_detail is None and i.started_at
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_detail_text_stored(session):
    i = await _inst(session)
    seen = []
    a, b, c = _run(session, [{"status": "created", "detail": "ContainerCreating"}, {"status": "running"}])
    orig = ir.asyncio.sleep

    async def spy(_):
        await session.refresh(i)
        seen.append(i.status_detail)
        await orig(0)
    with a, b, c, patch.object(ir.asyncio, "sleep", spy):
        await ir.wait_until_ready(i.id, interval=0)
    assert seen == ["Preparing (pulling image)"]


@pytest.mark.asyncio
async def test_fatal_after_grace_errors(session):
    i = await _inst(session)
    with patch.object(ir, "FATAL_GRACE", -1):
        await _wait(session, [{"status": "created", "detail": "ImagePullBackOff"}] * 3, iid=i.id)
    await session.refresh(i)
    assert i.status == "error"
    assert i.error_message == "Instance failed to start: ImagePullBackOff"


@pytest.mark.asyncio
async def test_timeout_errors(session):
    i = await _inst(session)
    await _wait(session, [{"status": "created", "detail": "Starting"}] * 5, iid=i.id, timeout=-1)
    await session.refresh(i)
    assert i.status == "error" and i.error_message == "Instance did not become ready in time"


@pytest.mark.asyncio
async def test_deleted_or_not_starting_returns(session):
    await _wait(session, [], missing=True)
    i = await _inst(session, status="stopped")
    await _wait(session, [], iid=i.id)
    await session.refresh(i)
    assert i.status == "stopped"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend,status,waits", [("k8s", "starting", 1), ("file", "running", 0)])
async def test_start_endpoint_backend_behaviour(
        admin_client, session, monkeypatch, backend, status, waits):
    from tests.test_instances_api import _make_owned_instance, shared_docker  # noqa: F401
    monkeypatch.setenv("ROUTE_BACKEND", backend)
    inst = await _make_owned_instance(session, status="stopped")
    with patch.object(ir, "start_waiting") as sw:
        r = await admin_client.post(f"/api/instances/{inst.id}/start")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == status
    assert sw.call_count == waits
    if waits:
        assert r.json()["status_detail"] == "Starting"
        sw.assert_called_once_with(inst.id)


@pytest.mark.asyncio
async def test_boot_reconcile_rewaits_starting_on_k8s(session, monkeypatch):
    from app.services.background_loops import _reconcile_instances_at_boot
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    i = await _inst(session)
    rt = MagicMock()
    rt.get_container_status.return_value = {"status": "created", "detail": "Starting"}
    with patch.object(ir, "start_waiting") as sw:
        await _reconcile_instances_at_boot(session, rt)
    sw.assert_called_once_with(i.id)
