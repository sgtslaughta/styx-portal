from unittest.mock import AsyncMock

import docker.errors
import pytest

import app.services.background_loops as main
import app.services.route_writer as route_writer
import app.services.workstations as workstations


@pytest.mark.asyncio
async def test_monitor_pass_docker_error_still_marks_workstations(monkeypatch):
    """With no Docker (k8s), the Docker pass raises every tick; workstation
    offline-marking and route refresh must still run."""
    async def failing_pass(session, monitor, dock):
        raise docker.errors.DockerException("no docker")

    mark = AsyncMock(return_value=True)
    refresh = AsyncMock()
    session = AsyncMock()

    monkeypatch.setattr(main, "_run_monitor_pass", failing_pass)
    monkeypatch.setattr(workstations, "mark_stale_offline", mark)
    monkeypatch.setattr(route_writer, "refresh_routes_from_db", refresh)

    await main._monitor_tick(session, object(), object())

    mark.assert_awaited_once_with(session)
    refresh.assert_awaited_once_with(session)
    session.commit.assert_awaited_once()


class _Docker:
    def __init__(self, fn):
        self.get_container_status = fn


async def _seed(session, statuses):
    from app.models import Instance
    insts = [Instance(name=f"i{n}", subdomain=f"s{n}", template_id="t", status=st, container_id=f"c{n}")
             for n, st in enumerate(statuses)]
    for i in insts:
        session.add(i)
    await session.commit()
    return insts


@pytest.mark.asyncio
async def test_boot_reconcile_survives_docker_down(session):
    insts = await _seed(session, ["running", "idle"])

    def boom(_cid):
        raise docker.errors.DockerException("no docker")

    await main._reconcile_instances_at_boot(session, _Docker(boom))
    for i in insts:
        await session.refresh(i)
        assert i.status == "stopped"


@pytest.mark.asyncio
async def test_boot_reconcile_docker_up_unchanged(session):
    up, gone = await _seed(session, ["running", "running"])
    st = {up.container_id: "running", gone.container_id: "not_found"}
    await main._reconcile_instances_at_boot(session, _Docker(lambda c: {"status": st[c]}))
    await session.refresh(up)
    await session.refresh(gone)
    assert (up.status, gone.status) == ("running", "stopped")
