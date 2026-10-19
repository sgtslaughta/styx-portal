"""Minimal in-cluster Kubernetes REST client (httpx, ServiceAccount token)."""
import json
import os

import httpx

_SA = "/var/run/secrets/kubernetes.io/serviceaccount"
_PLURALS = {
    "IngressRoute": "ingressroutes", "Middleware": "middlewares",
    "ServersTransport": "serverstransports", "Service": "services",
    "EndpointSlice": "endpointslices", "Pod": "pods",
}


def _base(api_version: str) -> str:
    return "/api/v1" if api_version == "v1" else f"/apis/{api_version}"


def _path(api_version: str, kind: str, namespace: str) -> str:
    return f"{_base(api_version)}/namespaces/{namespace}/{_PLURALS[kind]}"


class K8sClient:
    def __init__(self, base_url: str, token: str, verify: str | bool,
                 transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=base_url, verify=verify, timeout=10, transport=transport,
            headers={"Authorization": f"Bearer {token}"})

    @classmethod
    def from_incluster(cls) -> "K8sClient":
        host = os.environ["KUBERNETES_SERVICE_HOST"]
        port = os.environ["KUBERNETES_SERVICE_PORT"]
        host = f"[{host}]" if ":" in host else host
        with open(f"{_SA}/token") as f:
            token = f.read().strip()
        return cls(f"https://{host}:{port}", token, f"{_SA}/ca.crt")

    def apply(self, obj: dict) -> None:
        md = obj["metadata"]
        r = self._http.patch(
            f"{_path(obj['apiVersion'], obj['kind'], md['namespace'])}/{md['name']}",
            params={"fieldManager": "styx-backend", "force": "true"},
            content=json.dumps(obj),
            headers={"Content-Type": "application/apply-patch+yaml"})
        r.raise_for_status()

    def list_names(self, api_version: str, kind: str, namespace: str,
                   label_selector: str) -> list[str]:
        r = self._http.get(_path(api_version, kind, namespace),
                           params={"labelSelector": label_selector})
        r.raise_for_status()
        return [i["metadata"]["name"] for i in r.json().get("items", [])]

    def delete(self, api_version: str, kind: str, namespace: str,
               name: str) -> None:
        r = self._http.delete(f"{_path(api_version, kind, namespace)}/{name}")
        if r.status_code != 404:
            r.raise_for_status()

    def list_pod_ips(self, namespace: str, label_selector: str) -> set[str]:
        r = self._http.get(_path("v1", "Pod", namespace),
                           params={"labelSelector": label_selector})
        r.raise_for_status()
        return {i["status"]["podIP"] for i in r.json().get("items", [])
                if i.get("status", {}).get("phase") == "Running"
                and i["status"].get("podIP")}
