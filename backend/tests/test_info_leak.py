"""B7/B8/B9: generic enroll errors, docs off, banners."""
from unittest.mock import AsyncMock


# ---- B7 ---------------------------------------------------------------
async def test_enroll_503_is_generic(client, tmp_path, monkeypatch):
    from app.routers import enroll
    monkeypatch.setattr(enroll, "_agent_dir", lambda: tmp_path)
    r = await client.get("/api/enroll/script")
    assert r.status_code == 503
    assert "AGENT_DIR" not in r.text and "enroll.sh" not in r.text and str(tmp_path) not in r.text


async def test_artifact_503_is_generic(client, monkeypatch):
    from app.routers import enroll
    from app.services import artifacts
    monkeypatch.setattr(artifacts, "ensure_artifact",
                        AsyncMock(side_effect=artifacts.ArtifactMissing("/srv/cache/x missing")))
    name = next(iter(artifacts.ARTIFACTS))
    r = await client.get(f"/api/enroll/artifacts/{name}")
    assert r.status_code == 503
    assert "/srv" not in r.text and "ArtifactMissing" not in r.text
    assert enroll  # imported



# ---- B8 / B9 ----------------------------------------------------------
async def test_docs_disabled_by_default(client):
    for p in ("/docs", "/redoc", "/openapi.json", "/api/docs", "/api/openapi.json"):
        assert (await client.get(p)).status_code == 404


def test_docs_urls_follow_flag():
    from app.config import Settings
    from app.main import docs_kwargs
    assert docs_kwargs(Settings(ENABLE_DOCS=False)) == {
        "docs_url": None, "redoc_url": None, "openapi_url": None}
    assert docs_kwargs(Settings(ENABLE_DOCS=True)) == {}


def test_nginx_and_uvicorn_hardening():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    ngx = (root / "frontend/nginx.conf").read_text()
    assert "server_tokens off;" in ngx
    assert "Strict-Transport-Security" in ngx
    assert "--no-server-header" in (root / "backend/Dockerfile").read_text()
