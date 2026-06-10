import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models import Instance, ServiceTemplate
from app.services.route_writer import refresh_routes_from_db
from app.services.session_monitor import SessionMonitor
from app.main import _run_monitor_pass


@pytest.mark.asyncio
async def test_instance_unavailable_page(client):
    resp = await client.get("/api/instance-unavailable")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    # JS derives subdomain from the path and redirects to /?stopped=...
    assert "location.replace" in body
    assert "/i/" in body
    assert "stopped=" in body
    # no-JS fallback to My Instances
    assert 'href="/"' in body


async def _make_template(session):
    t = ServiceTemplate(
        name="t", display_name="T", image="img:latest",
        internal_port=3001, internal_protocol="https",
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


@pytest.mark.asyncio
async def test_refresh_routes_from_db_only_running(session, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.services.route_writer.write_routes",
        lambda data, domain=None, workstations=None: captured.setdefault("data", data),
    )
    t = await _make_template(session)
    session.add(Instance(template_id=t.id, name="a", subdomain="a", status="running", container_id="c-a"))
    session.add(Instance(template_id=t.id, name="b", subdomain="b", status="stopped", container_id=None))
    await session.commit()

    await refresh_routes_from_db(session)

    subs = {d["subdomain"] for d in captured["data"]}
    assert subs == {"a"}
    assert captured["data"][0]["protocol"] == "https"


@pytest.mark.asyncio
async def test_monitor_pass_marks_crashed_container_stopped(session):
    t = await _make_template(session)
    inst = Instance(template_id=t.id, name="x", subdomain="x", status="running", container_id="c-x")
    session.add(inst)
    await session.commit()

    docker = MagicMock()
    docker.get_container_status.return_value = {"status": "exited"}
    monitor = SessionMonitor(docker)

    changed = await _run_monitor_pass(session, monitor, docker)
    await session.commit()
    await session.refresh(inst)

    assert changed is True
    assert inst.status == "stopped"


@pytest.mark.asyncio
async def test_monitor_pass_auto_stops_idle(session):
    t = await _make_template(session)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    inst = Instance(
        template_id=t.id, name="y", subdomain="y", status="idle",
        container_id="c-y", last_activity=old, started_at=old,
        session_config={"idle_timeout": "30m", "grace_period": "5m"},
    )
    session.add(inst)
    await session.commit()

    docker = MagicMock()
    docker.get_container_status.return_value = {"status": "running"}
    docker.stop_container.return_value = None
    monitor = SessionMonitor(docker)

    changed = await _run_monitor_pass(session, monitor, docker)
    await session.commit()
    await session.refresh(inst)

    assert changed is True
    assert inst.status == "stopped"
