import json

import httpx
import pytest

from app.services.k8s_api import K8sClient
from app.services.k8s_instances import K8sInstanceRuntime

NS = "styx-instances"
DEP = f"/apis/apps/v1/namespaces/{NS}/deployments/selkies-a"


class Rec:
    def __init__(self, responses=None):
        self.reqs, self.responses = [], responses or {}

    def __call__(self, r):
        self.reqs.append(r)
        return self.responses.get((r.method, r.url.path), httpx.Response(200, json={}))

    def runtime(self):
        return K8sInstanceRuntime(K8sClient("https://k8s", "t", False,
                                            transport=httpx.MockTransport(self)))

    def find(self, method, path):
        return [r for r in self.reqs if r.method == method and r.url.path == path]


def test_noop_and_stub_methods():
    rt = Rec().runtime()
    assert rt.image_exists("x") is True
    assert rt.pull_image_streaming("x") is None
    assert rt.get_image_info("x") == {"size_mb": 0, "id": "x"}
    assert rt.ensure_user_network("u1") == "u1"
    assert rt.ensure_isolated("c", "u1") is None
    assert rt.remove_user_network("u1") is None
    assert rt.on_portal_network() == []
    assert rt.get_container_stats("x") == {}


def test_volumes():
    rec = Rec()
    rt = rec.runtime()
    assert rt.create_volume("vol-1") == "vol-1"
    (p,) = rec.find("PATCH", f"/api/v1/namespaces/{NS}/persistentvolumeclaims/vol-1")
    assert json.loads(p.content)["kind"] == "PersistentVolumeClaim"
    rt.remove_volume("vol-1")
    assert rec.find("DELETE", f"/api/v1/namespaces/{NS}/persistentvolumeclaims/vol-1")


def _create(rt, **kw):
    args = dict(name="selkies-a", image="selkies-desktop:latest", labels={"x": "y"},
                environment={}, volumes={"vol-1": {"bind": "/config"}}, port=3000,
                network="u1", restart_policy="always", ulimits=[{"name": "nofile"}],
                devices=["/dev/foo"], security_opt=["seccomp=unconfined"],
                extra_docker_args={"a": 1}, cap_add=["CHOWN"])
    args.update(kw)
    return rt.create_container(**args)


def test_create_container_applies_deployment_and_service():
    rec = Rec()
    assert _create(rec.runtime()) == "selkies-a"
    dep = json.loads(rec.find("PATCH", DEP)[0].content)
    assert dep["spec"]["replicas"] == 0
    assert dep["metadata"]["labels"]["styx/owner"] == "u1"
    assert rec.find("PATCH", f"/api/v1/namespaces/{NS}/services/selkies-a")


def test_create_container_refuses_privileged_and_dind():
    rec = Rec()
    for kw in ({"privileged": True}, {"dind": True}):
        with pytest.raises(ValueError):
            _create(rec.runtime(), **kw)
    assert not rec.reqs


def test_lifecycle_patches():
    rec = Rec()
    rt = rec.runtime()
    rt.start_container("selkies-a")
    rt.stop_container("selkies-a")
    rt.restart_container("selkies-a")
    bodies = [json.loads(r.content) for r in rec.find("PATCH", DEP)]
    assert bodies[0] == {"spec": {"replicas": 1}}
    assert bodies[1] == {"spec": {"replicas": 0}}
    ann = bodies[2]["spec"]["template"]["metadata"]["annotations"]
    assert "styx/restartedAt" in ann
    assert rec.reqs[0].headers["content-type"] == "application/merge-patch+json"


def test_pause_unsupported():
    rt = Rec().runtime()
    for f in (rt.pause_container, rt.unpause_container):
        with pytest.raises(NotImplementedError):
            f("selkies-a")


def test_remove_container_deletes_deployment_and_service():
    rec = Rec()
    Rec.runtime(rec).remove_container("selkies-a")
    assert rec.find("DELETE", DEP)
    assert rec.find("DELETE", f"/api/v1/namespaces/{NS}/services/selkies-a")


def _status(dep, pods=None):
    r = {("GET", DEP): httpx.Response(404, json={}) if dep is None
         else httpx.Response(200, json=dep)}
    r[("GET", f"/api/v1/namespaces/{NS}/pods")] = httpx.Response(
        200, json={"items": pods or []})
    return Rec(r).runtime().get_container_status("selkies-a")


def test_status_mapping():
    assert _status(None) == {"status": "not_found"}
    assert _status({"spec": {"replicas": 0}, "status": {}})["status"] == "exited"
    assert _status({"spec": {"replicas": 1}, "status": {}})["status"] == "created"
    s = _status({"spec": {"replicas": 1}, "status": {"readyReplicas": 1}},
                [{"status": {"startTime": "2026-01-01T00:00:00Z"}}])
    assert s == {"status": "running", "started_at": "2026-01-01T00:00:00Z"}
    assert _status({"spec": {"replicas": 1}, "status": {"readyReplicas": 1}})["started_at"] == ""


def test_container_logs():
    rec = Rec({
        ("GET", f"/api/v1/namespaces/{NS}/pods"): httpx.Response(
            200, json={"items": [{"metadata": {"name": "selkies-a-xyz"}}]}),
        ("GET", f"/api/v1/namespaces/{NS}/pods/selkies-a-xyz/log"): httpx.Response(
            200, text="l1\nl2\n")})
    assert rec.runtime().instance_logs("selkies-a", 50) == ["l1", "l2"]
    (g,) = rec.find("GET", f"/api/v1/namespaces/{NS}/pods/selkies-a-xyz/log")
    assert g.url.params["tailLines"] == "50" and g.url.params["timestamps"] == "true"
    assert Rec().runtime().instance_logs("selkies-a", 50) == []


MET = "/apis/metrics.k8s.io/v1beta1/namespaces/styx-instances/pods"


def _usage(metrics, dep=None):
    r = {("GET", MET): httpx.Response(200, json={"items": metrics})}
    r[("GET", DEP)] = httpx.Response(404, json={}) if dep is None else httpx.Response(200, json=dep)
    rec = Rec(r)
    return rec, rec.runtime().instance_usage("selkies-a")


def test_instance_usage_percentages():
    dep = {"spec": {"template": {"spec": {"containers": [
        {"resources": {"limits": {"cpu": "2", "memory": "4Gi"}}}]}}}}
    rec, u = _usage([{"containers": [{"usage": {"cpu": "500m", "memory": "1Gi"}},
                                     {"usage": {"cpu": "500000000n", "memory": "1Gi"}}]}], dep)
    assert u == {"cpu_percent": 50.0, "memory_mb": 2048, "memory_limit_mb": 4096,
                 "memory_percent": 50.0}
    (g,) = rec.find("GET", MET)
    assert g.url.params["labelSelector"] == "app=selkies-a"


def test_instance_usage_missing_is_zeros():
    zero = {"cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0}
    assert _usage([])[1] == zero
    assert Rec({("GET", MET): httpx.Response(404, json={})}).runtime() \
        .instance_usage("selkies-a") == zero
