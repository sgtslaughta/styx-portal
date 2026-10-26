"""Container-runtime stand-in for k8s: cluster Services as 'docker-local' targets.
A Service is named `<svc>.<ns>.svc` (cluster DNS)."""
import re

from app.config import Settings
from app.services.k8s_api import incluster_client

SKIP_NS = {"kube-system", "kube-public", "kube-node-lease"}
_NAME = re.compile(r"^([a-z0-9-]+)\.([a-z0-9-]+)\.svc$")


class K8sRuntime:
    def __init__(self, client=None):
        self._c = client or incluster_client()

    def list_containers(self) -> list[dict]:
        skip = SKIP_NS | {Settings().K8S_NAMESPACE}
        out = []
        for s in (self._c.get_json("/api/v1/services") or {}).get("items", []):
            md, spec = s["metadata"], s.get("spec", {})
            ns = md["namespace"]
            ports = sorted({p["port"] for p in spec.get("ports") or []
                            if p.get("protocol", "TCP") == "TCP"})
            if ns in skip or not ports or spec.get("type") == "ExternalName":
                continue
            sel = spec.get("selector") or {}
            out.append({
                "name": f"{md['name']}.{ns}.svc",
                "image": sel.get("app.kubernetes.io/name") or sel.get("app") or "",
                "ports": ports, "networks": [ns]})
        return out

    def container_health(self, name: str) -> str:
        m = _NAME.match(name)
        if not m:
            return "unknown"
        svc, ns = m[1], m[2]
        try:
            if self._c.get_json(f"/api/v1/namespaces/{ns}/services/{svc}") is None:
                return "unhealthy"
            data = self._c.get_json(
                f"/apis/discovery.k8s.io/v1/namespaces/{ns}/endpointslices",
                {"labelSelector": f"kubernetes.io/service-name={svc}"}) or {}
            for sl in data.get("items", []):
                for e in sl.get("endpoints") or []:
                    if (e.get("conditions") or {}).get("ready"):
                        return "healthy"
            return "unhealthy"
        except Exception:
            return "unknown"

    def ensure_traefik_network(self, name: str) -> None:
        pass

    def connect_to_network(self, container: str, network: str) -> bool:
        return True

    def disconnect_from_network(self, container: str, network: str) -> None:
        pass


def container_runtime():
    if Settings().ROUTE_BACKEND == "k8s":
        return K8sRuntime()
    from app.services.docker_manager import DockerManager
    return DockerManager(network_name=Settings().DOCKER_NETWORK)
