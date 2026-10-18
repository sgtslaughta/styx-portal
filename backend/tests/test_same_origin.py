"""R-A3 mitigations: Focus-cookie write guard and admin-write origin check."""
import pytest

from app.models import ProxiedService
from app.services.service_routes import focus_value


async def _focus_cookie(client, session, mount="cookie-root"):
    s = ProxiedService(slug="unraid", name="U", kind="url", upstream_url="http://10.0.0.2",
                       auth_mode="sso", bypass_rules=[], mount_mode=mount)
    session.add(s)
    await session.commit()
    client.cookies.set("styx_svc", focus_value(s.slug, s.id), path="/")


async def test_focus_cookie_blocks_api_writes(admin_client, session):
    await _focus_cookie(admin_client, session)
    r = await admin_client.post("/api/groups", json={"name": "x"})
    assert r.status_code == 403 and "focus" in r.json()["detail"].lower()
    assert (await admin_client.get("/api/groups")).status_code == 200      # reads untouched


async def test_focus_cookie_allowlist_keeps_spa_working(admin_client, session):
    await _focus_cookie(admin_client, session)
    r = await admin_client.put("/api/auth/me/preferences", json={"open_mode": "shell"})
    assert r.status_code != 403 or "focus" not in r.json().get("detail", "").lower()
    assert (await admin_client.post("/api/auth/refresh")).status_code == 200
    admin_client.headers["X-CSRF-Token"] = admin_client.cookies.get("csrf_token")  # rotated
    r = await admin_client.post("/api/auth/logout")
    assert r.status_code in (200, 204), r.text


async def test_stale_or_path_mode_cookie_is_not_focus(admin_client, session):
    admin_client.cookies.set("styx_svc", "gone.deadbeef0000", path="/")
    assert (await admin_client.post("/api/groups", json={"name": "a"})).status_code in (200, 201)
    await _focus_cookie(admin_client, session, mount="path")
    assert (await admin_client.post("/api/groups", json={"name": "b"})).status_code in (200, 201)


@pytest.mark.parametrize("headers,ok", [
    ({}, True),                                                      # non-browser client
    ({"sec-fetch-dest": "empty", "referer": "http://test/admin/groups"}, True),
    ({"sec-fetch-dest": "empty", "origin": "http://test"}, True),   # no referer, matching origin
    ({"sec-fetch-dest": "empty"}, False),                            # no referer, no origin
    ({"sec-fetch-dest": "empty", "origin": "http://evil"}, False),
    ({"sec-fetch-dest": "iframe", "referer": "http://test/groups"}, False),
    ({"sec-fetch-dest": "empty", "referer": "http://test/i/dev/app"}, False),
    ({"sec-fetch-dest": "empty", "referer": "http://test/w/box/"}, False),
    ({"sec-fetch-dest": "empty", "referer": "http://test/_styx/app/sonarr/"}, False),
    ({"sec-fetch-dest": "empty", "referer": "http://test/sonarr/ui"}, False),   # service slug
])
async def test_admin_write_origin_check(admin_client, session, headers, ok):
    session.add(ProxiedService(slug="sonarr", name="S", kind="url", upstream_url="http://10.0.0.3",
                               auth_mode="sso", bypass_rules=[]))
    await session.commit()
    r = await admin_client.post("/api/groups", json={"name": "g"}, headers=headers)
    assert (r.status_code in (200, 201)) is ok, r.text


async def test_member_writes_unaffected_by_admin_origin_check(member_client):
    r = await member_client.put("/api/auth/me/preferences", json={"open_mode": "shell"},
                                headers={"sec-fetch-dest": "empty"})
    assert r.status_code != 403
