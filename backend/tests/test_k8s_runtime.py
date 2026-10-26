from app.services.k8s_runtime import K8sRuntime


def _svc(name, ns, ports=({"port": 80, "protocol": "TCP"},), type_="ClusterIP",
         labels=None, selector=None):
    return {"metadata": {"name": name, "namespace": ns, "labels": labels or {}},
            "spec": {"type": type_, "ports": list(ports),
                     "selector": selector or {}}}


class Fake:
    def __init__(self, data=None, exc=None):
        self.data, self.exc, self.calls = data or {}, exc, []

    def get_json(self, path, params=None):
        self.calls.append((path, params))
        if self.exc:
            raise self.exc
        return self.data.get(path)


def test_list_containers_filters_and_shape():
    items = [
        _svc("sonarr", "media", ports=[{"port": 8989, "protocol": "TCP"},
                                       {"port": 53, "protocol": "UDP"},
                                       {"port": 80, "protocol": "TCP"}],
             selector={"app.kubernetes.io/name": "sonarr-img"}),
        _svc("dns", "kube-system"),
        _svc("backend", "styx"),
        _svc("noports", "media", ports=[]),
        _svc("ext", "media", type_="ExternalName"),
        _svc("plain", "apps", selector={"app": "plain-app"}),
        _svc("bare", "apps"),
    ]
    rt = K8sRuntime(Fake({"/api/v1/services": {"items": items}}))
    out = rt.list_containers()
    assert out == [
        {"name": "sonarr.media.svc", "image": "sonarr-img",
         "ports": [80, 8989], "networks": ["media"]},
        {"name": "plain.apps.svc", "image": "plain-app",
         "ports": [80], "networks": ["apps"]},
        {"name": "bare.apps.svc", "image": "", "ports": [80],
         "networks": ["apps"]},
    ]


EP = "/apis/discovery.k8s.io/v1/namespaces/media/endpointslices"
SV = "/api/v1/namespaces/media/services/sonarr"


def _eps(*ready):
    return {"items": [{"endpoints": [{"conditions": {"ready": r}}
                                     for r in ready]}]}


def test_health_healthy():
    f = Fake({SV: {}, EP: _eps(False, True)})
    assert K8sRuntime(f).container_health("sonarr.media.svc") == "healthy"
    assert f.calls[-1][1] == {"labelSelector": "kubernetes.io/service-name=sonarr"}


def test_health_unhealthy_none_ready():
    assert K8sRuntime(Fake({SV: {}, EP: _eps(False)})
                      ).container_health("sonarr.media.svc") == "unhealthy"


def test_health_service_missing():
    assert K8sRuntime(Fake({})).container_health(
        "sonarr.media.svc") == "unhealthy"


def test_health_bad_name():
    assert K8sRuntime(Fake()).container_health("sonarr") == "unknown"


def test_health_exception():
    assert K8sRuntime(Fake(exc=RuntimeError("x"))).container_health(
        "sonarr.media.svc") == "unknown"


def test_noop_network_methods():
    rt = K8sRuntime(Fake())
    rt.ensure_traefik_network("n")
    assert rt.connect_to_network("c", "n") is True
    rt.disconnect_from_network("c", "n")
