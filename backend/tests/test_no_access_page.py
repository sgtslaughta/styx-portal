"""403 on navigations is a Styx page (forwardAuth relays the body); XHR keeps JSON."""
import pytest

from app.models import ProxiedService
from app.routers import services_auth

NAV = {"x-forwarded-uri": "/sonarr/", "x-forwarded-host": "localhost",
       "sec-fetch-mode": "navigate"}
SAME = {"sec-fetch-site": "same-origin"}
XHR = {"x-forwarded-uri": "/sonarr/", "accept": "application/json"}


async def _svc(session):
    session.add(ProxiedService(slug="sonarr", name="Sonarr", kind="url",
                               upstream_url="http://10.0.0.2:8989", auth_mode="sso",
                               bypass_rules=[], allowed_groups=["ops"]))
    await session.commit()


@pytest.mark.asyncio
async def test_service_nav_403_is_html_page(member_client, session):
    await _svc(session)
    r = await member_client.get("/internal/services/sonarr/auth-check", headers=NAV)
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("text/html")
    assert "No access" in r.text and 'href="/_styx/exit"' in r.text
    assert "sonarr" not in r.text.lower()


@pytest.mark.asyncio
async def test_service_xhr_403_stays_json(member_client, session):
    await _svc(session)
    r = await member_client.get("/internal/services/sonarr/auth-check", headers=XHR)
    assert r.status_code == 403
    assert r.json()["detail"] == "No access to this service"


@pytest.mark.asyncio
async def test_workstation_unknown_nav_html_xhr_json(member_client):
    url = "/internal/workstations/nope/auth-check"
    r = await member_client.get(url, headers=NAV)
    assert r.status_code == 403 and r.headers["content-type"].startswith("text/html")
    r = await member_client.get(url, headers=XHR)
    assert r.status_code == 403 and "detail" in r.json()


@pytest.mark.asyncio
async def test_instance_other_owner_nav_html_xhr_json(member_client, session):
    from tests.test_instance_auth_check import _inst, _owner, auth
    await _inst(session, await _owner(session))
    r = await member_client.get(auth(), headers={**NAV, "x-forwarded-uri": "/i/dev/"})
    assert r.status_code == 403 and r.headers["content-type"].startswith("text/html")
    r = await member_client.get(auth(), headers=XHR)
    assert r.status_code == 403 and "detail" in r.json()


@pytest.mark.asyncio
async def test_open_cookie_follows_cookie_secure(member_client, session, monkeypatch):
    s = ProxiedService(slug="unraid", name="U", kind="url", upstream_url="http://10.0.0.2:80",
                       auth_mode="sso", bypass_rules=[], mount_mode="cookie-root")
    session.add(s)
    await session.commit()
    r = await member_client.get("/_styx/open/unraid", headers=SAME, follow_redirects=False)
    assert "styx_svc=unraid" in r.headers["set-cookie"]
    assert "secure" not in r.headers["set-cookie"].lower()  # suite runs COOKIE_SECURE=false
    monkeypatch.setattr(services_auth._settings, "COOKIE_SECURE", True)
    r = await member_client.get("/_styx/open/unraid", headers=SAME, follow_redirects=False)
    assert "secure" in r.headers["set-cookie"].lower()
