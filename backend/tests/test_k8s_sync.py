import json
import logging

import httpx
import pytest

from app.services import route_writer
from app.services.k8s_api import K8sClient
from app.services.k8s_routes import K8sSyncError, sync_objects, to_k8s_objects
from app.services.route_writer import build_routes_config

IR = "/apis/traefik.io/v1alpha1/namespaces/styx/ingressroutes"


def _client(handler):
    return K8sClient("https://k8s", "tok", False,
                     transport=httpx.MockTransport(handler))


def _ws():
    return {"id": "ws1", "subdomain": "desk", "lan_ip": "192.168.1.50",
            "port": 8443, "protocol": "http"}


def _desired():
    cfg = build_routes_config([], "s.example", "tunnel", workstations=[_ws()])
    return to_k8s_objects(cfg, "styx")


def test_apply_uses_server_side_apply():
    seen = []
    c = _client(lambda r: (seen.append(r), httpx.Response(200, json={}))[1])
    ir = next(o for o in _desired() if o["kind"] == "IngressRoute"
              and o["metadata"]["name"] == "ws-ws1")
    c.apply(ir)
    (r,) = seen
    assert r.method == "PATCH"
    assert r.url.path == f"{IR}/ws-ws1"
    assert r.url.params["fieldManager"] == "styx-backend"
    assert r.url.params["force"] == "true"
    assert r.headers["content-type"] == "application/apply-patch+yaml"
    assert r.headers["authorization"] == "Bearer tok"
    assert json.loads(r.content)["kind"] == "IngressRoute"


def test_core_kind_path():
    seen = []
    c = _client(lambda r: (seen.append(r), httpx.Response(200, json={}))[1])
    c.apply(next(o for o in _desired() if o["kind"] == "Service"
                 and o["metadata"]["name"] == "ws-ws1"))
    assert seen[0].url.path == "/api/v1/namespaces/styx/services/ws-ws1"


def test_sync_prunes_stale_managed_objects():
    reqs = []

    def handler(r):
        reqs.append(r)
        if r.method == "GET":
            names = ["ws-old", "ws-ws1"] if r.url.path == IR else []
            return httpx.Response(200, json={
                "items": [{"metadata": {"name": n}} for n in names]})
        return httpx.Response(200, json={})

    sync_objects(_client(handler), _desired(), "styx")
    deletes = [r for r in reqs if r.method == "DELETE"]
    assert [d.url.path for d in deletes] == [f"{IR}/ws-old"]
    gets = [r for r in reqs if r.method == "GET"]
    assert len(gets) == 5
    assert gets[0].url.params["labelSelector"] == \
        "app.kubernetes.io/managed-by=styx-backend"
    # apply happens before prune
    first_get = reqs.index(gets[0])
    assert all(r.method == "PATCH" for r in reqs[:first_get])


def test_delete_404_ignored():
    c = _client(lambda r: httpx.Response(404, json={}))
    c.delete("traefik.io/v1alpha1", "IngressRoute", "styx", "gone")


def test_list_pod_ips_running_only():
    def handler(r):
        assert r.url.path == "/api/v1/namespaces/styx/pods"
        assert r.url.params["labelSelector"] == "app=x"
        return httpx.Response(200, json={"items": [
            {"status": {"phase": "Running", "podIP": "10.0.0.1"}},
            {"status": {"phase": "Pending", "podIP": "10.0.0.2"}},
            {"status": {"phase": "Running"}},
        ]})

    assert _client(handler).list_pod_ips("styx", "app=x") == {"10.0.0.1"}


def _k8s_mode(monkeypatch, handler):
    monkeypatch.setattr(route_writer._settings, "ROUTE_BACKEND", "k8s")
    monkeypatch.setattr(route_writer, "_k8s_client", _client(handler))


def test_write_routes_k8s_api_error_logged_not_raised(monkeypatch, caplog):
    _k8s_mode(monkeypatch, lambda r: httpx.Response(403, json={}))
    with caplog.at_level(logging.ERROR, logger="styx-portal"):
        route_writer.write_routes([])
    assert "k8s" in caplog.text
    with pytest.raises(K8sSyncError):
        route_writer.write_routes([], strict=True)


def test_write_routes_k8s_applies_objects(monkeypatch):
    seen = []

    def handler(r):
        seen.append(r)
        return httpx.Response(200, json={"items": []})

    _k8s_mode(monkeypatch, handler)
    route_writer.write_routes([])
    assert any(r.method == "PATCH" and r.url.path == f"{IR}/frontend"
               for r in seen)


def test_build_routes_config_k8s_skips_lan_and_services(tmp_path, monkeypatch):
    (tmp_path / "lan.crt").write_text("c")
    (tmp_path / "lan.key").write_text("k")
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    svc = {"id": "s1", "slug": "sonarr", "upstream": "http://sonarr:8989",
           "mount_mode": "path", "auth_mode": "styx", "verify_tls": True,
           "enabled": True, "upstream_host": None}
    cfg = build_routes_config([], "s.example", "tunnel", workstations=[_ws()],
                              services=[svc], k8s=True)
    routers = cfg["http"]["routers"]
    assert not [n for n in routers if n.endswith("-lan")]
    assert "tls" not in cfg
    assert "ws-ws1" in routers
    plain = build_routes_config([], "s.example", "tunnel",
                                workstations=[_ws()], services=[svc])
    assert [n for n in plain["http"]["routers"] if "sonarr" in n]
    assert not [n for n in routers if "sonarr" in n]


@pytest.mark.asyncio
async def test_refresh_routes_runs_write_off_loop(monkeypatch):
    import threading

    class _R:
        def all(self):
            return []

    class _S:
        async def exec(self, *_):
            return _R()

    seen = []
    monkeypatch.setattr(route_writer, "write_routes",
                        lambda *a, **k: seen.append(threading.current_thread()))
    await route_writer.refresh_routes_from_db(_S())
    assert seen and seen[0] is not threading.main_thread()


@pytest.mark.asyncio
async def test_refresh_routes_strict_error_propagates(monkeypatch):
    class _R:
        def all(self):
            return []

    class _S:
        async def exec(self, *_):
            return _R()

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(route_writer, "write_routes", boom)
    with pytest.raises(RuntimeError):
        await route_writer.refresh_routes_from_db(_S(), strict=True)


def test_token_reread_after_ttl(tmp_path, monkeypatch):
    from app.services import k8s_api
    tok = tmp_path / "token"
    tok.write_text("old")
    seen = []
    c = K8sClient("https://k8s", "old", False, token_path=str(tok),
                  transport=httpx.MockTransport(
                      lambda r: (seen.append(r), httpx.Response(200, json={}))[1]))
    now = [1000.0]
    monkeypatch.setattr(k8s_api.time, "monotonic", lambda: now[0])
    c._token_read = now[0]
    tok.write_text("new\n")
    c.list_names("v1", "Service", "styx", "a=b")
    assert seen[-1].headers["authorization"] == "Bearer old"
    now[0] += 61
    c.list_names("v1", "Service", "styx", "a=b")
    assert seen[-1].headers["authorization"] == "Bearer new"


def test_error_message_includes_response_body():
    c = _client(lambda r: httpx.Response(422, text="spec.routes: Invalid"))
    obj = next(o for o in _desired() if o["kind"] == "IngressRoute")
    with pytest.raises(httpx.HTTPStatusError, match="spec.routes: Invalid"):
        c.apply(obj)


def test_sync_continues_after_one_apply_failure():
    reqs = []

    def handler(r):
        reqs.append(r)
        n = sum(1 for x in reqs if x.method == "PATCH")
        if r.method == "PATCH" and n == 2:
            return httpx.Response(422, text="bad spec")
        return httpx.Response(200, json={"items": []})

    desired = _desired()[:3]
    with pytest.raises(K8sSyncError, match="1/3"):
        sync_objects(_client(handler), desired, "styx")
    assert sum(r.method == "PATCH" for r in reqs) == 3
    assert not [r for r in reqs if r.method in ("DELETE", "GET")]
