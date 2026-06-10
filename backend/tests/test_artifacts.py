import pytest

from app.services import artifacts


@pytest.mark.asyncio
async def test_cached_file_served_without_download(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies.tar.gz").write_bytes(b"cached-bytes")
    path = await artifacts.ensure_selkies_tarball()
    assert path.read_bytes() == b"cached-bytes"


@pytest.mark.asyncio
async def test_downloads_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))

    async def fake_download(url, dest):
        dest.write_bytes(b"downloaded")
    monkeypatch.setattr(artifacts, "_download", fake_download)
    path = await artifacts.ensure_selkies_tarball()
    assert path.read_bytes() == b"downloaded"


@pytest.mark.asyncio
async def test_download_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))

    async def boom(url, dest):
        raise ConnectionError("no route")
    monkeypatch.setattr(artifacts, "_download", boom)
    with pytest.raises(ConnectionError):
        await artifacts.ensure_selkies_tarball()
