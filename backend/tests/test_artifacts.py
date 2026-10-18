import pytest

from app.services import artifacts


def test_no_anonymously_triggered_upstream_download():
    """Unused selkies-app artifact removed: no endpoint may fetch from the internet."""
    assert "selkies-app.tar.gz" not in artifacts.ARTIFACTS
    assert all(url is None for url in artifacts.ARTIFACTS.values())


@pytest.mark.asyncio
async def test_prebuilt_artifact_never_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    with pytest.raises(artifacts.ArtifactMissing) as e:
        await artifacts.ensure_artifact("wheelhouse-x86_64.tar.gz")
    assert "build_agent_artifacts" in str(e.value)


@pytest.mark.asyncio
async def test_prebuilt_artifact_served_when_placed(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "wheelhouse-x86_64.tar.gz").write_bytes(b"web")
    path = await artifacts.ensure_artifact("wheelhouse-x86_64.tar.gz")
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


def test_artifacts_for_selkies2():
    assert "selkies-web.tar.gz" not in artifacts.ARTIFACTS
    assert "libshim-x86_64.tar.gz" not in artifacts.ARTIFACTS
    assert "wheelhouse-x86_64.tar.gz" in artifacts.ARTIFACTS
