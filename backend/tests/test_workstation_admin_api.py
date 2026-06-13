import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from app.main import app
from app.models import User, Workstation, WorkstationAccess
from app.security.crypto import encrypt_secret
from app.security.passwords import hash_password


async def _seed(session):
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        admin = User(username="admin", password_hash=hash_password("admin-password"), role="admin")
        session.add(admin)
        await session.commit()
    user = User(username="carol", password_hash=hash_password("x"), role="user")
    session.add(user)
    await session.commit()
    ws = Workstation(name="desk", subdomain="desk", hostname="desk",
                     lan_ip="192.168.1.50", status="online",
                     selkies_password_enc=encrypt_secret("pw123"),
                     created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws, user


@pytest.mark.asyncio
async def test_list_admin_only(admin_client, session):
    ws, _ = await _seed(session)
    # Create a fresh unauthenticated client for the first check
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh_client:
        r = await fresh_client.get("/api/workstations")
        assert r.status_code == 401
    # Admin client can list
    r = await admin_client.get("/api/workstations")
    assert r.status_code == 200
    assert r.json()[0]["subdomain"] == "desk"


@pytest.mark.asyncio
async def test_patch_settings_and_access(admin_client, session):
    ws, user = await _seed(session)
    r = await admin_client.patch(f"/api/workstations/{ws.id}", json={
        "name": "Gaming rig", "stream_settings": {"encoder": "nvh264enc",
                                                  "framerate": 120,
                                                  "bitrate_kbps": 40000}})
    assert r.status_code == 200
    assert r.json()["stream_settings"]["framerate"] == 120
    r = await admin_client.put(f"/api/workstations/{ws.id}/access",
                               json={"user_ids": [user.id]})
    assert r.status_code == 200
    assert r.json()["allowed_user_ids"] == [user.id]


@pytest.mark.asyncio
async def test_delete_revokes_then_purges(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.delete(f"/api/workstations/{ws.id}")
    assert r.status_code == 200
    await session.refresh(ws)
    assert ws.status == "revoked"
    r = await admin_client.delete(f"/api/workstations/{ws.id}?purge=true")
    assert r.status_code == 200
    assert (await session.get(Workstation, ws.id)) is None


@pytest.mark.asyncio
async def test_mine_and_connect_respect_access(admin_client, client, session):
    ws, user = await _seed(session)
    # login as carol
    await client.get("/api/auth/csrf")
    login = await client.post("/api/auth/login",
                              json={"username": "carol", "password": "x"})
    assert login.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers["X-CSRF-Token"] = csrf or ""

    r = await client.get("/api/workstations/mine")
    assert r.status_code == 200 and r.json() == []
    r = await client.get(f"/api/workstations/{ws.id}/connect")
    assert r.status_code == 403

    session.add(WorkstationAccess(workstation_id=ws.id, user_id=user.id))
    await session.commit()
    r = await client.get("/api/workstations/mine")
    assert [w["id"] for w in r.json()] == [ws.id]
    r = await client.get(f"/api/workstations/{ws.id}/connect")
    assert r.status_code == 200
    assert "/w/desk/" in r.json()["url"]
    assert "password" not in r.json()["url"]


@pytest.mark.asyncio
async def test_auth_check_no_cookie_unauthorized(session):
    ws, _ = await _seed(session)
    # Create a fresh unauthenticated client
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh_client:
        r = await fresh_client.get("/api/workstations/auth-check",
                                   headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_check_browser_navigation_redirects_to_login(session):
    """Unauthenticated browser hit on /w/{sub}/ gets a login redirect with a
    next param, not raw 401 JSON (Traefik relays forwardAuth errors as-is)."""
    ws, _ = await _seed(session)
    from httpx import ASGITransport, AsyncClient
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as fresh_client:
        # Location must be ABSOLUTE on the original host — Traefik resolves a
        # relative Location against the auth-server URL (http://backend:8000).
        # Test settings: DOMAIN=localhost.
        r = await fresh_client.get("/api/workstations/auth-check", headers={
            "X-Forwarded-Uri": f"/w/{ws.subdomain}/",
            "X-Forwarded-Proto": "https", "X-Forwarded-Host": "localhost",
            "Sec-Fetch-Mode": "navigate"})
        assert r.status_code == 302
        assert r.headers["location"] == \
            f"https://localhost/login?next=/w/{ws.subdomain}/"
        # Accept: text/html also counts as a navigation (older browsers)
        r = await fresh_client.get("/api/workstations/auth-check", headers={
            "X-Forwarded-Uri": f"/w/{ws.subdomain}/",
            "Accept": "text/html,application/xhtml+xml"})
        assert r.status_code == 302
        # Forged X-Forwarded-Host falls back to DOMAIN (no host-header redirect)
        r = await fresh_client.get("/api/workstations/auth-check", headers={
            "X-Forwarded-Uri": f"/w/{ws.subdomain}/",
            "X-Forwarded-Proto": "https", "X-Forwarded-Host": "evil.example",
            "Sec-Fetch-Mode": "navigate"})
        assert r.status_code == 302
        assert r.headers["location"].startswith("https://localhost/login")
        # Private LAN IP hosts are honored (host-agnostic LAN routers)
        r = await fresh_client.get("/api/workstations/auth-check", headers={
            "X-Forwarded-Uri": f"/w/{ws.subdomain}/",
            "X-Forwarded-Proto": "https", "X-Forwarded-Host": "192.168.1.10:443",
            "Sec-Fetch-Mode": "navigate"})
        assert r.status_code == 302
        assert r.headers["location"].startswith("https://192.168.1.10:443/login")
        # Unrecognized URI shape: redirect to login WITHOUT next (no open redirect)
        r = await fresh_client.get("/api/workstations/auth-check", headers={
            "X-Forwarded-Uri": "https://evil.example/phish",
            "X-Forwarded-Proto": "https", "X-Forwarded-Host": "localhost",
            "Sec-Fetch-Mode": "navigate"})
        assert r.status_code == 302
        assert r.headers["location"] == "https://localhost/login"
        # Non-navigation (websocket/XHR) keeps the 401
        r = await fresh_client.get("/api/workstations/auth-check", headers={
            "X-Forwarded-Uri": f"/w/{ws.subdomain}/websockets"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_occupancy_records_and_gates_connect(admin_client, client, session):
    """ws-upgrade auth records the occupant; agent-reported connections make
    it live; a second user's connect is 423 unless force=true; the occupant
    reconnects freely; zero connections clears occupancy."""
    ws, user = await _seed(session)
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=user.id))
    ws.status = "online"
    session.add(ws)
    await session.commit()
    # carol logs in (admin_client and client share the cookie jar) and her
    # websocket upgrade passes auth-check -> she becomes the occupant
    await client.get("/api/auth/csrf")
    assert (await client.post("/api/auth/login",
            json={"username": "carol", "password": "x"})).status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token") or ""
    r = await client.get("/api/workstations/auth-check", headers={
        "X-Forwarded-Uri": f"/w/{ws.subdomain}/websockets"})
    assert r.status_code == 200
    await session.refresh(ws)
    assert ws.occupied_by == user.id
    # agent reports a live connection
    ws.active_connections = 1
    session.add(ws)
    await session.commit()
    # carol sees herself as the occupant and reconnects without force
    mine = (await client.get("/api/workstations/mine")).json()
    assert next(w for w in mine if w["id"] == ws.id)["in_use_self"] is True
    assert (await client.get(
        f"/api/workstations/{ws.id}/connect")).status_code == 200
    # switch back to admin (different user): blocked without force
    assert (await client.post("/api/auth/login", json={
        "username": "admin",
        "password": "correct horse battery staple"})).status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token") or ""
    r = await client.get(f"/api/workstations/{ws.id}/connect")
    assert r.status_code == 423
    assert "carol" in r.json()["detail"]
    assert (await client.get(
        f"/api/workstations/{ws.id}/connect?force=true")).status_code == 200
    rows = (await client.get("/api/workstations")).json()
    row = next(w for w in rows if w["id"] == ws.id)
    assert row["in_use"] is True and row["in_use_by"] == "carol"
    # heartbeat with zero connections clears occupancy
    from app.services.workstations import sha256_hex as _sha
    import secrets as _secrets
    raw_agent = _secrets.token_urlsafe(16)
    ws.agent_token_hash = _sha(raw_agent)
    session.add(ws)
    await session.commit()
    r = await client.post("/api/agent/heartbeat",
                          headers={"Authorization": f"Bearer {raw_agent}"},
                          json={"status": "online",
                                "health": {"active_connections": 0}})
    assert r.status_code == 200
    await session.refresh(ws)
    assert ws.active_connections == 0 and ws.occupied_by is None


@pytest.mark.asyncio
async def test_auth_check_with_access_allowed(admin_client, client, session):
    ws, user = await _seed(session)
    # Login as carol
    await client.get("/api/auth/csrf")
    login = await client.post("/api/auth/login",
                              json={"username": "carol", "password": "x"})
    assert login.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers["X-CSRF-Token"] = csrf or ""

    # Grant access and check auth-check allows
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=user.id))
    await session.commit()
    r = await client.get("/api/workstations/auth-check",
                         headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.asyncio
async def test_auth_check_without_access_forbidden(admin_client, client, session):
    ws, user = await _seed(session)
    # Login as carol (no access granted)
    await client.get("/api/auth/csrf")
    login = await client.post("/api/auth/login",
                              json={"username": "carol", "password": "x"})
    assert login.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers["X-CSRF-Token"] = csrf or ""

    r = await client.get("/api/workstations/auth-check",
                         headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_auth_check_admin_always_allowed(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.get("/api/workstations/auth-check",
                               headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_check_bad_uri_forbidden(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.get("/api/workstations/auth-check",
                               headers={"X-Forwarded-Uri": "/bad/path/"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_auth_check_unknown_workstation_forbidden(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.get("/api/workstations/auth-check",
                               headers={"X-Forwarded-Uri": "/w/unknown/"})
    assert r.status_code == 403


def test_get_latest_agent_version_parses_served_file(tmp_path):
    from app.services.workstations import get_latest_agent_version, _version_cache
    _version_cache.clear()
    (tmp_path / "styx_agent.py").write_text('X = 1\nAGENT_VERSION = "0.9.3"\nY = 2\n')
    assert get_latest_agent_version(str(tmp_path)) == "0.9.3"


def test_get_latest_agent_version_missing_file_returns_empty(tmp_path):
    from app.services.workstations import get_latest_agent_version, _version_cache
    _version_cache.clear()
    assert get_latest_agent_version(str(tmp_path / "nope")) == ""


@pytest.mark.asyncio
async def test_list_marks_outdated_agents(admin_client, session, monkeypatch):
    import app.routers.workstations as wr
    from app.models import User, Workstation
    from sqlmodel import select
    monkeypatch.setattr(wr, "get_latest_agent_version", lambda: "0.4.2")
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    for sub, ver in [("a", "0.4.1"), ("b", "0.4.2"), ("c", "")]:
        session.add(Workstation(name=sub, subdomain=sub, hostname=sub,
                                status="online", agent_version=ver,
                                created_by=admin.id))
    await session.commit()

    r = await admin_client.get("/api/workstations")
    assert r.status_code == 200
    by_sub = {w["subdomain"]: w["agent_outdated"] for w in r.json()}
    assert by_sub["a"] is True
    assert by_sub["b"] is False
    assert by_sub["c"] is False


def test_build_update_command_pulls_files_and_restarts():
    from app.services.workstations import build_update_command
    cmd = build_update_command("https://styx.example.com")
    assert "https://styx.example.com/api/enroll/${f%%:*}" in cmd
    assert "agent.py:styx_agent.py" in cmd
    assert "gateway.py:gateway.py" in cmd
    assert "systemctl --user restart styx-agent" in cmd
    assert "curl -fsSL " in cmd
    assert " -k " not in cmd


def test_build_update_command_insecure_for_lan():
    from app.services.workstations import build_update_command
    cmd = build_update_command("https://192.168.1.10", insecure=True)
    assert "curl -fsSLk " in cmd
