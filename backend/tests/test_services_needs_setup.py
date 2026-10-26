"""needs_setup: docker-local path-mounted app whose preset Styx can configure, not yet confirmed."""
import pytest

from app.models import ProxiedService, ServicePreset

CFG = {"methods": [{"type": "config_file", "paths": ["/c.xml"], "format": "xml", "key": "/C/U"}]}
ENV = {"methods": [{"type": "env", "name": "BASE"}]}


@pytest.fixture(autouse=True)
async def presets(session):
    session.add(ServicePreset(id="jellyfin", name="Jellyfin", subpath=CFG))
    session.add(ServicePreset(id="envapp", name="Env", subpath=ENV))
    await session.commit()


def _svc(slug, **kw):
    d = dict(slug=slug, name=slug, kind="docker-local", container=slug, container_port=80,
             mount_mode="path", preset_id="jellyfin")
    d.update(kw)
    return ProxiedService(**d)


CASES = [
    ("yes", {}, True),
    ("managed", {"mount_managed": True}, False),
    ("cookie", {"mount_mode": "cookie-root"}, False),
    ("urlkind", {"kind": "url", "container": None, "upstream_url": "http://x:1"}, False),
    ("nopreset", {"preset_id": None}, False),
    ("noconfig", {"preset_id": "envapp"}, False),
]


@pytest.mark.parametrize("slug,kw,want", CASES)
async def test_admin_out_needs_setup(admin_client, session, slug, kw, want):
    session.add(_svc(slug, **kw))
    await session.commit()
    rows = {r["slug"]: r for r in (await admin_client.get("/api/services")).json()}
    assert rows[slug]["needs_setup"] is want


async def test_member_list_excludes_needs_setup(member_client, session):
    session.add(_svc("pending", allowed_groups=[], auth_mode="sso"))
    session.add(_svc("ready", mount_managed=True))
    await session.commit()
    slugs = {r["slug"] for r in (await member_client.get("/api/services")).json()}
    assert "pending" not in slugs and "ready" in slugs


async def test_k8s_service_is_never_needs_setup(admin_client, session, monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    session.add(_svc("yes"))
    await session.commit()
    rows = {r["slug"]: r for r in (await admin_client.get("/api/services")).json()}
    assert rows["yes"]["needs_setup"] is False
