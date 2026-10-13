import tarfile
from unittest.mock import MagicMock
import pytest
from app.main import app
from app.models import AuditLog, ProxiedService, ServicePreset
from app.routers import services as services_router
from sqlmodel import select

SUB = {"methods": [{"type": "config_file", "paths": ["/config/config.xml"], "format": "xml",
                    "key": "/Config/UrlBase"}], "restart": True, "verify_path": "/{slug}/ping"}


@pytest.fixture
def dk(monkeypatch):
    d = MagicMock()
    d.read_file.return_value = (b"<Config><UrlBase/></Config>", tarfile.TarInfo("c"))
    d.container_labels.return_value = {}
    app.dependency_overrides[services_router.get_docker_manager] = lambda: d
    started = []
    monkeypatch.setattr("app.routers.service_mounts._start", lambda *a, **k: started.append(a))
    yield d, started
    app.dependency_overrides.pop(services_router.get_docker_manager, None)


async def _svc(session):
    session.add(ServicePreset(id="sonarr", name="Sonarr", subpath=SUB))
    s = ProxiedService(slug="sonarr", name="Sonarr", kind="docker-local", container="sonarr",
                       container_port=8989, preset_id="sonarr")
    session.add(s)
    await session.commit()
    return s


async def test_plan(admin_client, session, dk):
    s = await _svc(session)
    r = await admin_client.post(f"/api/services/{s.id}/mount/plan")
    assert r.status_code == 200 and r.json()["needs_consent"] is True
    assert r.json()["changes"][0]["new"] == "/sonarr"


async def test_apply_requires_consent_for_adopted(admin_client, session, dk):
    s = await _svc(session)
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": False})
    assert r.status_code == 409


async def test_apply_with_consent_starts_and_audits(admin_client, session, dk):
    s = await _svc(session)
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    assert r.status_code == 202 and r.json()["job_id"] and len(dk[1]) == 1
    logs = (await session.exec(select(AuditLog).where(AuditLog.action == "service.mount_apply"))).all()
    assert logs and "/sonarr" in str(logs[0].detail)


async def test_second_apply_conflicts(admin_client, session, dk):
    s = await _svc(session)
    await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    assert r.status_code == 409 and "already running" in r.json()["detail"]


async def test_manual_plan_cannot_apply(admin_client, session, dk):
    s = await _svc(session)
    dk[0].read_file.return_value = None
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    assert r.status_code == 409 and "can't find" in r.json()["detail"]


async def test_latest_job(admin_client, session, dk):
    s = await _svc(session)
    assert (await admin_client.get(f"/api/services/{s.id}/mount/jobs/latest")).status_code == 404
    await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    j = (await admin_client.get(f"/api/services/{s.id}/mount/jobs/latest")).json()
    assert j["state"] == "pending" and j["changes"][0]["new"] == "/sonarr"
    assert j["changed"] is False


async def test_member_forbidden(member_client, session, dk):
    s = await _svc(session)
    assert (await member_client.post(f"/api/services/{s.id}/mount/plan")).status_code == 403


async def test_concurrent_applies_start_one_job(admin_client, session, dk):
    import asyncio
    s = await _svc(session)
    body = {"consent": True}
    rs = await asyncio.gather(*[admin_client.post(f"/api/services/{s.id}/mount/apply", json=body)
                                for _ in range(4)])
    assert sorted(r.status_code for r in rs) == [202, 409, 409, 409] and len(dk[1]) == 1


async def test_apply_rejects_changes_that_moved_since_review(admin_client, session, dk):
    s = await _svc(session)
    seen = (await admin_client.post(f"/api/services/{s.id}/mount/plan")).json()["changes"]
    dk[0].read_file.return_value = (b"<Config><UrlBase>/other</UrlBase></Config>", tarfile.TarInfo("c"))
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply",
                                json={"consent": True, "changes": seen})
    assert r.status_code == 409 and "Review again" in r.json()["detail"]
    assert dk[1] == []


async def test_apply_accepts_matching_changes(admin_client, session, dk):
    s = await _svc(session)
    seen = (await admin_client.post(f"/api/services/{s.id}/mount/plan")).json()["changes"]
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply",
                                json={"consent": True, "changes": seen})
    assert r.status_code == 202
