from unittest.mock import AsyncMock

import docker.errors
import pytest

import app.main as main
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
