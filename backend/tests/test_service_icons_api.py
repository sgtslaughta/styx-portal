import base64

import pytest
from sqlmodel import select

from app.models import AuditLog, Group, ProxiedService
from app.services import service_favicon

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()


@pytest.fixture(autouse=True)
def no_route_write(monkeypatch):
    async def fake(session, **kw):
        return None
    monkeypatch.setattr("app.services.route_writer.refresh_routes_from_db", fake)


@pytest.fixture
def scheduled(monkeypatch):
    calls = []
    monkeypatch.setattr(service_favicon, "schedule_favicon", lambda *a, **k: calls.append(a))
    return calls


async def _svc(session, **kw) -> ProxiedService:
    d = dict(slug="sonarr", name="Sonarr", kind="url", upstream_url="http://10.0.0.2:8989")
    d.update(kw)
    s = ProxiedService(**d)
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return s


@pytest.mark.asyncio
async def test_put_icon_sets_custom_and_audits(admin_client, session):
    s = await _svc(session, icon=PNG_URI)
    r = await admin_client.put(f"/api/services/{s.id}/icon", json={"kind": "emoji", "value": "📺"})
    assert r.status_code == 200 and r.json()["icon_kind"] == "emoji"
    assert "icon" not in r.json()
    await session.refresh(s)
    assert s.icon == "emoji:📺" and s.icon_custom is True
    r = await admin_client.put(f"/api/services/{s.id}/icon", json={"kind": "auto"})
    await session.refresh(s)
    assert s.icon is None and s.icon_custom is True and r.json()["icon_kind"] == "auto"
    r = await admin_client.put(f"/api/services/{s.id}/icon", json={"kind": "image", "value": PNG_URI})
    assert r.json()["icon_kind"] == "image" and r.json()["icon_etag"]
    log = (await session.exec(select(AuditLog).where(AuditLog.action == "service.icon_change"))).all()
    assert len(log) == 3 and log[0].resource == s.id


@pytest.mark.asyncio
async def test_put_icon_invalid_400_and_member_403(admin_client, session):
    s = await _svc(session)
    r = await admin_client.put(f"/api/services/{s.id}/icon", json={"kind": "image", "value": "data:x"})
    assert r.status_code == 400
    r = await admin_client.put("/api/services/nope/icon", json={"kind": "auto"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_member_cannot_put_or_refresh(member_client, session):
    s = await _svc(session)
    assert (await member_client.put(f"/api/services/{s.id}/icon", json={"kind": "auto"})).status_code == 403
    assert (await member_client.post(f"/api/services/{s.id}/icon/refresh")).status_code == 403


@pytest.mark.asyncio
async def test_refresh_stores_and_clears_custom(admin_client, session, monkeypatch):
    s = await _svc(session, icon="emoji:📺", icon_custom=True)

    async def fake(svc, docker, **kw):
        return PNG_URI
    monkeypatch.setattr(service_favicon, "fetch_favicon", fake)
    r = await admin_client.post(f"/api/services/{s.id}/icon/refresh")
    assert r.status_code == 200 and r.json()["icon_kind"] == "image"
    await session.refresh(s)
    assert s.icon == PNG_URI and s.icon_custom is False
    log = (await session.exec(select(AuditLog).where(AuditLog.action == "service.icon_refresh"))).first()
    assert log is not None and log.resource == s.id


@pytest.mark.asyncio
async def test_refresh_none_found_422_icon_unchanged(admin_client, session, monkeypatch):
    s = await _svc(session, icon="emoji:📺", icon_custom=True)

    async def fake(svc, docker, **kw):
        return None
    monkeypatch.setattr(service_favicon, "fetch_favicon", fake)
    r = await admin_client.post(f"/api/services/{s.id}/icon/refresh")
    assert r.status_code == 422 and r.json()["detail"] == "Couldn't find an icon for Sonarr."
    await session.refresh(s)
    assert s.icon == "emoji:📺" and s.icon_custom is True


@pytest.mark.asyncio
async def test_get_icon_member_with_and_without_access(member_client, session):
    g = Group(name="media")
    session.add(g)
    await session.commit()
    open_s = await _svc(session, icon=PNG_URI)
    r = await member_client.get(f"/api/services/{open_s.id}/icon")
    assert r.status_code == 200 and r.content == PNG and r.headers["content-type"] == "image/png"
    closed = await _svc(session, slug="locked", name="Locked", allowed_groups=["media"], icon=PNG_URI)
    assert (await member_client.get(f"/api/services/{closed.id}/icon")).status_code == 404
    assert (await member_client.get("/api/services/nope/icon")).status_code == 404


@pytest.mark.asyncio
async def test_get_icon_requires_login(client, session):
    s = await _svc(session)
    assert (await client.get(f"/api/services/{s.id}/icon")).status_code == 401


@pytest.mark.asyncio
async def test_get_icon_admin_auto_badge_and_etag(admin_client, session):
    s = await _svc(session)
    r = await admin_client.get(f"/api/services/{s.id}/icon")
    assert r.status_code == 200 and r.headers["content-type"] == "image/svg+xml"
    n = await admin_client.get(f"/api/services/{s.id}/icon", headers={"If-None-Match": r.headers["etag"]})
    assert n.status_code == 304


@pytest.mark.asyncio
async def test_admin_list_carries_kind_and_etag_not_raw_icon(admin_client, session):
    await _svc(session, icon=PNG_URI)
    row = (await admin_client.get("/api/services")).json()[0]
    assert row["icon_kind"] == "image" and row["icon_etag"] and "icon" not in row


@pytest.mark.asyncio
async def test_member_tiles_carry_kind_and_etag_not_raw_icon(member_client, session):
    await _svc(session, icon=PNG_URI)
    row = (await member_client.get("/api/services")).json()[0]
    assert row["icon_kind"] == "image" and row["icon_etag"] and "icon" not in row


@pytest.mark.asyncio
async def test_create_normalises_preset_emoji_and_schedules_fetch(admin_client, scheduled):
    body = {"slug": "sonarr", "name": "Sonarr", "kind": "url", "upstream_url": "http://10.0.0.2:8989",
            "icon": "📺"}
    r = await admin_client.post("/api/services", json=body)
    assert r.status_code == 201 and r.json()["icon_kind"] == "emoji"
    assert len(scheduled) == 1 and scheduled[0][0] == r.json()["id"]
    r = await admin_client.post("/api/services", json={**body, "slug": "two", "icon": "not an emoji"})
    assert r.status_code == 422
    r = await admin_client.post("/api/services", json={**body, "slug": "three", "icon": PNG_URI})
    assert r.status_code == 201 and r.json()["icon_kind"] == "image"
    assert len(scheduled) == 1          # a hand-supplied image is custom: no auto fetch


@pytest.mark.asyncio
async def test_update_leaves_icon_alone_when_omitted(admin_client, session, scheduled):
    s = await _svc(session, icon="emoji:📺", icon_custom=True)
    body = {"slug": "sonarr", "name": "Sonarr2", "kind": "url", "upstream_url": "http://10.0.0.2:8989"}
    r = await admin_client.put(f"/api/services/{s.id}", json=body)
    assert r.status_code == 200
    await session.refresh(s)
    assert s.icon == "emoji:📺" and s.icon_custom is True


@pytest.mark.asyncio
async def test_background_fetch_skips_custom_and_stores_otherwise(session, monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def factory():
        yield session

    async def fake(svc, docker, **kw):
        return PNG_URI
    monkeypatch.setattr(service_favicon, "fetch_favicon", fake)
    custom = await _svc(session, icon="emoji:📺", icon_custom=True)
    plain = await _svc(session, slug="b", name="B")
    await service_favicon.fetch_and_store(factory, custom.id, None)
    await service_favicon.fetch_and_store(factory, plain.id, None)
    await session.refresh(custom)
    await session.refresh(plain)
    assert custom.icon == "emoji:📺" and plain.icon == PNG_URI


@pytest.mark.asyncio
async def test_member_icon_404_for_disabled_and_needs_setup(member_client, session):
    from app.models import ServicePreset
    session.add(ServicePreset(id="sonarr", name="Sonarr", subpath={"methods": [{"type": "config_file"}]}))
    await session.commit()
    off = await _svc(session, slug="off", name="Off", enabled=False, icon=PNG_URI)
    setup = await _svc(session, slug="ns", name="Ns", kind="docker-local", container="ns",
                       container_port=1, preset_id="sonarr", icon=PNG_URI)
    ok = await _svc(session, slug="ok", name="Ok", icon=PNG_URI)
    assert (await member_client.get(f"/api/services/{off.id}/icon")).status_code == 404
    assert (await member_client.get(f"/api/services/{setup.id}/icon")).status_code == 404
    assert (await member_client.get(f"/api/services/{ok.id}/icon")).status_code == 200


@pytest.mark.asyncio
async def test_admin_icon_200_for_disabled_and_needs_setup(admin_client, session):
    from app.models import ServicePreset
    session.add(ServicePreset(id="sonarr", name="Sonarr", subpath={"methods": [{"type": "config_file"}]}))
    await session.commit()
    off = await _svc(session, slug="off", name="Off", enabled=False)
    setup = await _svc(session, slug="ns", name="Ns", kind="docker-local", container="ns",
                       container_port=1, preset_id="sonarr")
    for s in (off, setup):
        assert (await admin_client.get(f"/api/services/{s.id}/icon")).status_code == 200
