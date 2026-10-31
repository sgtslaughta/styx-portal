import pytest

from app.main import app
from app.models import Instance
from app.routers import instance_thumbs
from app.routers.instances import get_screenshot_service
from app.services.screenshot import ScreenshotService

WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


@pytest.fixture(autouse=True)
def _thumb_dir(tmp_path, monkeypatch, client):
    monkeypatch.setattr(instance_thumbs, "thumb_dir", lambda: tmp_path)
    instance_thumbs._last_upload.clear()
    app.dependency_overrides[get_screenshot_service] = lambda: ScreenshotService(str(tmp_path), None)
    yield


async def _mk(session, owner_id, sub="thumb1"):
    inst = Instance(template_id="t", name="n", subdomain=sub, owner_id=owner_id, status="running")
    session.add(inst)
    await session.commit()
    return inst.id


async def _admin_id(admin_client):
    return (await admin_client.get("/api/auth/me")).json()["id"]


def _put(c, iid, body, ctype="image/webp"):
    return c.put(f"/api/instances/{iid}/screenshot", content=body, headers={"content-type": ctype})


@pytest.mark.asyncio
async def test_upload_then_get(admin_client, session):
    iid = await _mk(session, await _admin_id(admin_client))
    assert (await _put(admin_client, iid, WEBP)).status_code == 200
    r = await admin_client.get(f"/api/instances/{iid}/screenshot")
    assert r.status_code == 200 and r.content == WEBP
    assert r.headers["content-type"] == "image/webp"


@pytest.mark.asyncio
async def test_upload_jpeg_ok(admin_client, session):
    iid = await _mk(session, await _admin_id(admin_client))
    assert (await _put(admin_client, iid, JPEG, "image/jpeg")).status_code == 200


@pytest.mark.asyncio
async def test_too_big_413(admin_client, session):
    iid = await _mk(session, await _admin_id(admin_client))
    assert (await _put(admin_client, iid, WEBP + b"0" * 210_000)).status_code == 413


@pytest.mark.asyncio
async def test_bad_magic_415(admin_client, session):
    iid = await _mk(session, await _admin_id(admin_client))
    assert (await _put(admin_client, iid, b"<svg onload=x>")).status_code == 415


@pytest.mark.asyncio
async def test_other_user_403(member_client, session):
    iid = await _mk(session, "someone-else")
    assert (await _put(member_client, iid, WEBP)).status_code == 403


@pytest.mark.asyncio
async def test_unknown_instance_404(admin_client):
    assert (await _put(admin_client, "nope", WEBP)).status_code == 404


@pytest.mark.asyncio
async def test_rate_limited_204_ignored(admin_client, session):
    iid = await _mk(session, await _admin_id(admin_client))
    assert (await _put(admin_client, iid, WEBP)).status_code == 200
    r = await _put(admin_client, iid, JPEG, "image/jpeg")
    assert r.status_code == 204
    assert (await admin_client.get(f"/api/instances/{iid}/screenshot")).content == WEBP
