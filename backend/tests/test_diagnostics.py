import pytest

from app.services import diagnostics


class _FakeDocker:
    def __init__(self, ok=True): self._ok = ok
    def ping(self): return self._ok
    def version(self): return "29.5.2" if self._ok else None


@pytest.mark.asyncio
async def test_all_ok(session, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics._settings, "TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    (tmp_path / "routes.yml").write_text("x")
    result = await diagnostics.run_diagnostics(session, docker=_FakeDocker(True))
    keys = {c["key"] for c in result["checks"]}
    assert keys == {"docker", "database", "traefik_routes", "disk", "gpu"}
    assert all("latency_ms" in c for c in result["checks"])
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_docker_down_sets_not_ok(session, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics._settings, "TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    result = await diagnostics.run_diagnostics(session, docker=_FakeDocker(False))
    docker_check = next(c for c in result["checks"] if c["key"] == "docker")
    assert docker_check["ok"] is False
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_gpu_absence_is_informational(session, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics._settings, "TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    monkeypatch.setattr(diagnostics, "detect_gpu", lambda: {"available": False, "type": None})
    result = await diagnostics.run_diagnostics(session, docker=_FakeDocker(True))
    gpu = next(c for c in result["checks"] if c["key"] == "gpu")
    assert gpu["ok"] is True
