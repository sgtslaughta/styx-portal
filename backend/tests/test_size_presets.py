import pytest

DEFAULT = [
    {"id": "light", "label": "Light", "cpus": 2, "memory_gb": 2, "gpu": False},
    {"id": "standard", "label": "Standard", "cpus": 4, "memory_gb": 4, "gpu": False},
    {"id": "heavy", "label": "Heavy", "cpus": 6, "memory_gb": 8, "gpu": True},
]


@pytest.mark.asyncio
async def test_default_presets_for_member(member_client):
    r = await member_client.get("/api/system/size-presets")
    assert r.status_code == 200
    assert r.json() == DEFAULT


@pytest.mark.asyncio
async def test_presets_require_login(client):
    assert (await client.get("/api/system/size-presets")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_can_update_presets(admin_client):
    new = [DEFAULT[0]]
    r = await admin_client.patch("/api/system-settings", json={"CONTAINER_SIZE_PRESETS": new})
    assert r.status_code == 200, r.text
    assert (await admin_client.get("/api/system/size-presets")).json() == new


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [
    DEFAULT[:1] * 2,                                   # duplicate id
    [],                                                # too few
    [dict(DEFAULT[0], id=str(i)) for i in range(7)],   # too many
    [dict(DEFAULT[0], cpus=0)],
    [dict(DEFAULT[0], cpus=65)],
    [dict(DEFAULT[0], memory_gb=513)],
    [{"id": "x"}],
])
async def test_invalid_presets_422(admin_client, bad):
    r = await admin_client.patch("/api/system-settings", json={"CONTAINER_SIZE_PRESETS": bad})
    assert r.status_code == 422
