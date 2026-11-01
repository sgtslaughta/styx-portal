import hashlib
import pytest
from sqlmodel import select

from app.models import User, Workstation

LATEST = "0.9.32"


async def _admin(session):
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        from app.security.passwords import hash_password
        admin = User(username="adm-x", password_hash=hash_password("x"), role="admin")
        session.add(admin)
        await session.commit()
    return admin


async def _ws(session, sub="a", *, ver="0.9.31", status="online", token=None, **kw):
    admin = await _admin(session)
    ws = Workstation(name=sub, subdomain=sub, hostname=sub, status=status,
                     agent_version=ver, created_by=admin.id,
                     agent_token_hash=hashlib.sha256((token or sub).encode()).hexdigest(), **kw)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


@pytest.fixture(autouse=True)
def _latest(monkeypatch):
    import app.routers.agent as ar
    import app.routers.workstation_update as wu
    monkeypatch.setattr(ar, "get_latest_agent_version", lambda: LATEST)
    monkeypatch.setattr(wu, "get_latest_agent_version", lambda: LATEST)


def _auth(t="a"):
    return {"Authorization": f"Bearer {t}"}


async def _hb(client, t="a", health=None):
    r = await client.post("/api/agent/heartbeat", json={"health": health or {}},
                          headers=_auth(t))
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_request_update_sets_fields(admin_client, session):
    ws = await _ws(session)
    r = await admin_client.post(f"/api/workstations/{ws.id}/agent-update")
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["update_state"], j["update_target"], j["update_error"]) == ("requested", LATEST, None)
    await session.refresh(ws)
    assert ws.update_at is not None


@pytest.mark.asyncio
async def test_request_update_409_when_current(admin_client, session):
    ws = await _ws(session, ver=LATEST)
    assert (await admin_client.post(f"/api/workstations/{ws.id}/agent-update")).status_code == 409


@pytest.mark.asyncio
async def test_request_update_409_when_no_latest(admin_client, session, monkeypatch):
    import app.routers.workstation_update as wu
    monkeypatch.setattr(wu, "get_latest_agent_version", lambda: "")
    ws = await _ws(session)
    assert (await admin_client.post(f"/api/workstations/{ws.id}/agent-update")).status_code == 409


@pytest.mark.asyncio
async def test_update_outdated_counts_online_outdated(admin_client, session):
    a = await _ws(session, "a")
    await _ws(session, "b", ver=LATEST)
    await _ws(session, "c", status="offline")
    r = await admin_client.post("/api/workstations/agent-update-outdated")
    assert r.status_code == 200 and r.json() == {"requested": 1}
    await session.refresh(a)
    assert a.update_state == "requested"


@pytest.mark.asyncio
async def test_admin_only(member_client, session):
    ws = await _ws(session)
    assert (await member_client.post(f"/api/workstations/{ws.id}/agent-update")).status_code == 403
    assert (await member_client.post("/api/workstations/agent-update-outdated")).status_code == 403


@pytest.mark.asyncio
async def test_heartbeat_update_only_while_requested(client, session):
    ws = await _ws(session, update_target=LATEST, update_state="requested")
    assert (await _hb(client))["update"] == {"version": LATEST}
    ws.update_state = "updating"
    session.add(ws)
    await session.commit()
    assert (await _hb(client))["update"] is None


@pytest.mark.asyncio
async def test_health_update_applies_for_matching_target(client, session):
    ws = await _ws(session, update_target=LATEST, update_state="updating")
    await _hb(client, health={"update": {"state": "rolled_back", "from": "0.9.31",
                                         "to": LATEST, "error": "x" * 600}})
    await session.refresh(ws)
    assert ws.update_state == "rolled_back" and len(ws.update_error) == 500
    assert ws.update_at is not None


@pytest.mark.asyncio
async def test_health_update_ignored_for_other_target(client, session):
    ws = await _ws(session, update_target=LATEST, update_state="updating")
    await _hb(client, health={"update": {"state": "failed", "to": "0.1.0", "error": "e"}})
    await session.refresh(ws)
    assert ws.update_state == "updating"


@pytest.mark.asyncio
async def test_version_match_marks_ok(client, session):
    ws = await _ws(session, update_target=LATEST, update_state="updating")
    await _hb(client, health={"agent_version": LATEST})
    await session.refresh(ws)
    assert ws.update_state == "ok"


async def _auto_on():
    from app.services.settings_store import settings
    settings._overrides["AGENT_AUTO_UPDATE"] = True


@pytest.mark.asyncio
async def test_auto_mode_requests(client, session):
    ws = await _ws(session)
    assert (await _hb(client))["update"] is None   # setting off
    await session.refresh(ws)
    assert ws.update_state == ""
    await _auto_on()
    assert (await _hb(client))["update"] == {"version": LATEST}
    await session.refresh(ws)
    assert ws.update_state == "requested" and ws.update_target == LATEST


@pytest.mark.asyncio
async def test_auto_mode_not_after_rollback(client, session):
    ws = await _ws(session, update_target=LATEST, update_state="rolled_back")
    await _auto_on()
    assert (await _hb(client))["update"] is None
    await session.refresh(ws)
    assert ws.update_state == "rolled_back"


def test_manifest_hashes_and_deps(tmp_path, monkeypatch):
    import app.services.workstations as sw
    (tmp_path / "styx_agent.py").write_text('AGENT_VERSION = "0.9.31"\n')
    (tmp_path / "uninstall.sh").write_text("bye")
    (tmp_path / "enroll.sh").write_text("pip install selkies==2.1.0 pixelflux==2.2.1 pcmflux==2.2.0\n")
    monkeypatch.setattr(sw, "agent_dir", lambda: tmp_path)
    sw._version_cache.clear()
    monkeypatch.setattr(sw, "get_latest_agent_version", lambda *a: "0.9.31")
    m = sw.build_update_manifest()
    assert m["version"] == "0.9.31"
    assert m["deps"] == {"selkies": "2.1.0", "pixelflux": "2.2.1", "pcmflux": "2.2.0"}
    f = {x["remote"]: x for x in m["files"]}
    body = b'AGENT_VERSION = "0.9.31"\n'
    assert f["agent.py"] == {"remote": "agent.py", "local": "styx_agent.py",
                             "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}
    assert f["uninstall"]["local"] == "uninstall.sh" and f["uninstall"]["size"] == 3


@pytest.mark.asyncio
async def test_manifest_endpoint_auth(client, session):
    await _ws(session)
    assert (await client.get("/api/agent/update-manifest")).status_code == 401
    r = await client.get("/api/agent/update-manifest", headers=_auth())
    assert r.status_code == 200
    assert set(r.json()) == {"version", "files", "deps"}


@pytest.mark.asyncio
async def test_too_old_agent_409_and_skipped(admin_client, client, session):
    ws = await _ws(session, "old", ver="0.9.30")
    r = await admin_client.post(f"/api/workstations/{ws.id}/agent-update")
    assert r.status_code == 409 and "manual" in r.json()["detail"]
    r = await admin_client.post("/api/workstations/agent-update-outdated")
    assert r.json()["requested"] == 0
    await _auto_on()
    assert (await _hb(client, "old"))["update"] is None
