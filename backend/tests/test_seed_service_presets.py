import json
import os

import pytest
from sqlmodel import select

from app.database import seed_service_presets
from app.models import ServicePreset


@pytest.mark.asyncio
async def test_seed_inserts_once(session, tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({
        "id": "x", "name": "X", "default_port": 80, "mount_mode": "path", "auth_mode": "sso"}))
    await seed_service_presets(session, str(tmp_path))
    await seed_service_presets(session, str(tmp_path))
    rows = (await session.exec(select(ServicePreset))).all()
    assert len(rows) == 1 and rows[0].name == "X"


@pytest.mark.asyncio
async def test_repo_presets_load(session):
    here = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "services")
    await seed_service_presets(session, here)
    ids = {p.id for p in (await session.exec(select(ServicePreset))).all()}
    assert {"sonarr", "jellyfin", "audiobookshelf", "unraid", "generic-url"} <= ids
    ab = await session.get(ServicePreset, "audiobookshelf")
    assert ab.mount_mode == "cookie-root"


import pathlib  # noqa: E402

from app.schemas_services import BypassRule  # noqa: E402

PRESETS = pathlib.Path(__file__).resolve().parents[2] / "templates" / "services"


def test_servarr_presets_have_config_file_subpath():
    for app in ("sonarr", "radarr", "lidarr", "prowlarr"):
        sub = json.loads((PRESETS / f"{app}.json").read_text())["subpath"]
        assert sub["methods"][0] == {"type": "config_file", "paths": ["/config/config.xml"],
                                     "format": "xml", "key": "/Config/UrlBase"}
        assert sub["verify_path"] == "/{slug}/ping"


def test_jellyfin_native_rules():
    p = json.loads((PRESETS / "jellyfin.json").read_text())
    hdrs = {r.get("required_header") for r in p["bypass_rules"]}
    assert {"Authorization", "X-Emby-Authorization", "X-Emby-Token", "X-MediaBrowser-Token"} <= hdrs
    assert any(r.get("required_query") == "api_key" for r in p["bypass_rules"])
    assert p["auth_mode"] == "sso"  # native apps are opt-in (spec §5)


def test_focus_presets():
    for app in ("homeassistant", "immich"):
        assert json.loads((PRESETS / f"{app}.json").read_text())["mount_mode"] == "cookie-root"


def test_all_preset_bypass_rules_validate():
    for f in PRESETS.glob("*.json"):
        for r in json.loads(f.read_text()).get("bypass_rules", []):
            BypassRule(**r)


@pytest.mark.asyncio
async def test_seed_resets_fields_a_preset_dropped(session, tmp_path):
    session.add(ServicePreset(id="x", name="X", subpath={"methods": [{"type": "config_file"}]},
                              base_url_hint="old hint", warnings=["old"]))
    await session.commit()
    (tmp_path / "x.json").write_text(json.dumps({"id": "x", "name": "X2"}))
    await seed_service_presets(session, str(tmp_path))
    p = await session.get(ServicePreset, "x")
    await session.refresh(p)
    assert p.name == "X2" and p.subpath is None and p.base_url_hint is None and p.warnings == []
