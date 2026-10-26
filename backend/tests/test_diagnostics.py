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


class _FakeK8s:
    def __init__(self, routes=("a", "b"), version=True):
        self.routes, self.version = list(routes), version

    def get_json(self, path, params=None):
        assert path == "/version"
        if not self.version:
            raise RuntimeError("no api")
        return {"gitVersion": "v1.31.2+k3s1"}

    def list_names(self, api, kind, ns, selector):
        assert (api, kind, ns) == ("traefik.io/v1alpha1", "IngressRoute", "styx")
        assert selector == "app.kubernetes.io/managed-by=styx-backend"
        return self.routes


@pytest.mark.asyncio
async def test_k8s_checks(session, monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    monkeypatch.setattr(diagnostics, "incluster_client", lambda: _FakeK8s())
    result = await diagnostics.run_diagnostics(session)
    by = {c["key"]: c for c in result["checks"]}
    assert set(by) == {"kubernetes", "database", "traefik_routes", "disk", "gpu"}
    assert by["kubernetes"]["ok"] and "v1.31.2" in by["kubernetes"]["detail"]
    assert by["traefik_routes"]["ok"] and "2" in by["traefik_routes"]["detail"]
    assert by["gpu"]["detail"] == "amd.com/gpu via device plugin" and by["gpu"]["ok"]
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_k8s_checks_fail_without_api_or_routes(session, monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    monkeypatch.setattr(diagnostics, "incluster_client", lambda: _FakeK8s((), False))
    result = await diagnostics.run_diagnostics(session)
    by = {c["key"]: c for c in result["checks"]}
    assert by["kubernetes"]["ok"] is False and by["traefik_routes"]["ok"] is False
    assert result["ok"] is False
