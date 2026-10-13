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
