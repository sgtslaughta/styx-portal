from unittest.mock import MagicMock

import pytest

from app.main import app
from app.models import Instance, ServiceTemplate, User
from app.routers.instances import get_docker_manager
from app.services import k8s_runtime
from app.services.k8s_instances import K8sInstanceRuntime, K8sUnsupported
from app.services.k8s_routes import denied_namespaces, to_k8s_objects
from app.services.route_writer import build_routes_config


def _inst(**kw):
    return {"id": "i1", "subdomain": "dev", "port": 3000, "protocol": "http", **kw}


def test_route_writer_k8s_instance_upstream_is_cluster_service():
    cfg = build_routes_config([_inst()], "s.example", "tunnel", k8s=True)
    url = cfg["http"]["services"]["i1"]["loadBalancer"]["servers"][0]["url"]
    assert url == "http://selkies-dev.styx-instances.svc:3000"
    objs = to_k8s_objects(cfg, "styx")
    ir = next(o for o in objs if o["kind"] == "IngressRoute"
              and o["metadata"]["name"] == "i1")
    assert ir["spec"]["routes"][0]["services"] == [
        {"name": "selkies-dev", "namespace": "styx-instances", "port": 3000}]
    assert not [o for o in objs if o["kind"] == "Service"
                and o["metadata"]["name"] == "i1"]


def test_route_writer_compose_instance_upstream_unchanged():
    cfg = build_routes_config([_inst()], "s.example", "tunnel")
    assert cfg["http"]["services"]["i1"]["loadBalancer"]["servers"][0]["url"] \
        == "http://selkies-dev:3000"


def test_instance_namespace_never_denied(monkeypatch):
    monkeypatch.setenv("K8S_UPSTREAM_DENY_NAMESPACES", "styx-instances,default")
    assert "styx-instances" not in denied_namespaces()
    assert "default" in denied_namespaces()


def test_proxied_service_cannot_target_instance_namespace():
    s = {"id": "s1", "slug": "x", "upstream": "http://selkies-dev.styx-instances.svc:3000",
         "mount_mode": "path", "auth_mode": "styx", "verify_tls": True,
         "enabled": True, "upstream_host": None}
    cfg = build_routes_config([], "s.example", "tunnel", services=[s])
    assert not [o for o in to_k8s_objects(cfg, "styx") if o["kind"] == "IngressRoute"
                and "svc-x" in o["metadata"]["name"]]


def test_discovery_skips_instance_namespace():
    class F:
        def get_json(self, path, params=None):
            return {"items": [{"metadata": {"name": "a", "namespace": "styx-instances"},
                               "spec": {"ports": [{"port": 1, "protocol": "TCP"}]}}]}
    assert k8s_runtime.K8sRuntime(F()).list_containers() == []


def test_instance_runtime_factory(monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    monkeypatch.setattr("app.services.k8s_instances.incluster_client", lambda: MagicMock())
    assert isinstance(k8s_runtime.instance_runtime(), K8sInstanceRuntime)
    monkeypatch.setenv("ROUTE_BACKEND", "file")
    from app.services import docker_manager
    monkeypatch.setattr(docker_manager, "DockerManager", lambda network_name: ("d", network_name))
    assert k8s_runtime.instance_runtime()[0] == "d"


def test_pause_unsupported_is_422():
    assert K8sUnsupported("x").status_code == 422
    assert isinstance(K8sUnsupported("x"), NotImplementedError)


async def _owned(session, status="running"):
    from sqlmodel import select
    admin = (await session.exec(select(User).where(User.username == "admin"))).first()
    inst = Instance(template_id="t", owner_id=admin.id, name="o", subdomain="o",
                    container_id="selkies-o", status=status)
    session.add(inst)
    await session.commit()
    await session.refresh(inst)
    return inst


@pytest.fixture
def rt():
    m = MagicMock()
    app.dependency_overrides[get_docker_manager] = lambda: m
    yield m


@pytest.mark.asyncio
async def test_logs_endpoint_uses_runtime(admin_client, session, rt):
    inst = await _owned(session)
    rt.instance_logs.return_value = ["l1", "l2"]
    r = await admin_client.get(f"/api/instances/{inst.id}/logs?lines=10")
    assert r.json() == ["l1", "l2"]
    rt.instance_logs.assert_called_once_with("selkies-o", 10)


@pytest.mark.asyncio
async def test_pause_not_supported_returns_422(admin_client, session, rt):
    inst = await _owned(session)
    rt.pause_container.side_effect = K8sUnsupported("pause is not supported on Kubernetes")
    r = await admin_client.post(f"/api/instances/{inst.id}/pause")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_refused_template_is_422_on_k8s(admin_client, session, rt, monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    t = ServiceTemplate(name="dd", display_name="DD", image="x:1", dind=True,
                        memory_limit="4g", cpu_limit="2")
    session.add(t)
    await session.commit()
    r = await admin_client.post("/api/instances", json={
        "template_id": t.id, "name": "n", "subdomain": "dd"})
    assert r.status_code == 422
    assert "DinD" in r.json()["detail"]
    monkeypatch.setenv("ROUTE_BACKEND", "file")
    r = await admin_client.post("/api/instances", json={
        "template_id": t.id, "name": "n", "subdomain": "dd"})
    assert r.status_code == 201
