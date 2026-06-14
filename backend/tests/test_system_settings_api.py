async def test_get_settings_requires_admin(client):
    r = await client.get("/api/system-settings")
    assert r.status_code in (401, 403)


async def test_admin_gets_grouped_settings(admin_client):
    r = await admin_client.get("/api/system-settings")
    assert r.status_code == 200
    groups = r.json()
    keys = {s["key"] for g in groups for s in g["settings"]}
    assert "LOCKOUT_THRESHOLD" in keys


async def test_admin_patch_and_reset(admin_client):
    r = await admin_client.patch("/api/system-settings", json={"LOCKOUT_THRESHOLD": 4})
    assert r.status_code == 200, r.text
    g = await admin_client.get("/api/system-settings")
    val = next(s["value"] for grp in g.json() for s in grp["settings"]
               if s["key"] == "LOCKOUT_THRESHOLD")
    assert val == 4
    r2 = await admin_client.post("/api/system-settings/LOCKOUT_THRESHOLD/reset")
    assert r2.status_code == 200


async def test_patch_rejects_unknown_key(admin_client):
    r = await admin_client.patch("/api/system-settings", json={"NOPE": 1})
    assert r.status_code == 400


async def test_patch_rejects_out_of_bounds(admin_client):
    r = await admin_client.patch("/api/system-settings", json={"LOCKOUT_THRESHOLD": 0})
    assert r.status_code == 400
