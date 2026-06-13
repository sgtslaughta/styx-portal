import pytest

from app.services import artifacts


@pytest.mark.asyncio
async def test_url_artifact_cached_file_is_returned(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies-app.tar.gz").write_bytes(b"cached")
    path = await artifacts.ensure_artifact("selkies-app.tar.gz")
    assert path.read_bytes() == b"cached"


@pytest.mark.asyncio
async def test_url_artifact_downloads_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))

    async def fake_download(url, dest):
        dest.write_bytes(b"downloaded:" + url.encode())

    monkeypatch.setattr(artifacts, "_download", fake_download)
    path = await artifacts.ensure_artifact("selkies-app.tar.gz")
    assert path.read_bytes().startswith(b"downloaded:https://github.com/")


@pytest.mark.asyncio
async def test_prebuilt_artifact_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    with pytest.raises(artifacts.ArtifactMissing) as e:
        await artifacts.ensure_artifact("wheelhouse-x86_64.tar.gz")
    assert "build_agent_artifacts" in str(e.value)


@pytest.mark.asyncio
async def test_prebuilt_artifact_served_when_placed(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies-web.tar.gz").write_bytes(b"web")
    path = await artifacts.ensure_artifact("selkies-web.tar.gz")
    assert path.read_bytes() == b"web"


@pytest.mark.asyncio
async def test_nwg_shell_is_prebuilt_and_served(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    # Registered as prebuilt (None upstream): missing -> ArtifactMissing.
    assert artifacts.ARTIFACTS["nwg-shell-x86_64.tar.gz"] is None
    with pytest.raises(artifacts.ArtifactMissing):
        await artifacts.ensure_artifact("nwg-shell-x86_64.tar.gz")
    # Once placed by the build script, it is served as-is.
    (tmp_path / "nwg-shell-x86_64.tar.gz").write_bytes(b"nwg")
    path = await artifacts.ensure_artifact("nwg-shell-x86_64.tar.gz")
    assert path.read_bytes() == b"nwg"


@pytest.mark.asyncio
async def test_unknown_artifact_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    with pytest.raises(artifacts.ArtifactMissing):
        await artifacts.ensure_artifact("../../etc/passwd")
