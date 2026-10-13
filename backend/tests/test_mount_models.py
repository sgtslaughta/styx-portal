import json

from app.database import seed_service_presets
from app.models import MountJob, ProxiedService, ServicePreset
from app.schemas_services import BypassRule


def test_bypass_rule_accepts_prefix_and_query():
    r = BypassRule(path_prefix="/jellyfin/", required_header="Authorization",
                   header_prefix="MediaBrowser")
    assert r.header_prefix == "MediaBrowser"
    q = BypassRule(path_prefix="/jellyfin/", required_query="api_key")
    assert q.required_query == "api_key"


async def test_new_columns_default(session):
    s = ProxiedService(slug="x", name="X")
    session.add(s)
    await session.commit()
    await session.refresh(s)
    assert (s.mount_managed, s.pass_identity, s.frame_ok) == (False, False, True)


async def test_mount_job_roundtrip(session):
    j = MountJob(service_id="s1", steps=[{"id": "plan", "label": "Plan", "state": "done"}])
    session.add(j)
    await session.commit()
    await session.refresh(j)
    assert j.state == "pending" and j.steps[0]["id"] == "plan" and j.changes == []


async def test_seed_upserts_existing_preset(session, tmp_path):
    session.add(ServicePreset(id="sonarr", name="Old"))
    await session.commit()
    (tmp_path / "sonarr.json").write_text(json.dumps(
        {"id": "sonarr", "name": "Sonarr", "subpath": {"methods": []}}))
    await seed_service_presets(session, str(tmp_path))
    p = await session.get(ServicePreset, "sonarr")
    await session.refresh(p)
    assert p.name == "Sonarr" and p.subpath == {"methods": []}
