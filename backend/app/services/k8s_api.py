"""Minimal in-cluster Kubernetes REST client (httpx, ServiceAccount token)."""
import json
import logging
import os
import ssl
import threading
import time

import httpx

logger = logging.getLogger("styx-portal")
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


_TOKEN_TTL = 60  # projected SA tokens rotate; re-read the file this often


def _status_detail(r: httpx.Response) -> str:
    """Only code/reason/cause fields of a k8s Status; never message or raw
    body (a 422 message can echo submitted values such as credentials)."""
    try:
        body = r.json()
        causes = (body.get("details") or {}).get("causes") or []
        parts = [f"reason={body.get('reason')}"] + [
            f"{c.get('field')}:{c.get('reason')}" for c in causes]
        return " ".join(parts)
    except Exception:
        return ""


def _check(r: httpx.Response) -> None:
    if r.is_success:
        return
    raise httpx.HTTPStatusError(
        f"{r.request.method} {r.request.url.path} -> {r.status_code} "
        f"{_status_detail(r)}".rstrip(), request=r.request, response=r)


class K8sClient:
    def __init__(self, base_url: str, token: str, verify: ssl.SSLContext | bool,
                 transport: httpx.BaseTransport | None = None,
                 token_path: str | None = None):
        self._token = token
        self._token_path = token_path
        self._token_read = time.monotonic()
        self._http = httpx.Client(
            base_url=base_url, verify=verify, timeout=10, transport=transport)

    def _auth(self) -> dict:
        if self._token_path and time.monotonic() - self._token_read > _TOKEN_TTL:
            try:
                with open(self._token_path) as f:
                    self._token = f.read().strip()
            except OSError as e:
                if not self._token:
                    raise
                logger.warning("k8s token re-read failed, using cached: %s", e)
            self._token_read = time.monotonic()
        return {"Authorization": f"Bearer {self._token}"}

    @classmethod
    def from_incluster(cls) -> "K8sClient":
        host = os.environ["KUBERNETES_SERVICE_HOST"]
        port = os.environ["KUBERNETES_SERVICE_PORT"]
        host = f"[{host}]" if ":" in host else host
        with open(f"{_SA}/token") as f:
            token = f.read().strip()
        ctx = ssl.create_default_context(cafile=f"{_SA}/ca.crt")
        return cls(f"https://{host}:{port}", token, ctx,
                   token_path=f"{_SA}/token")

    def apply(self, obj: dict) -> None:
        md = obj["metadata"]
        r = self._http.patch(
            f"{_path(obj['apiVersion'], obj['kind'], md['namespace'])}/{md['name']}",
            params={"fieldManager": "styx-backend", "force": "true"},
            content=json.dumps(obj),
            headers={**self._auth(),
                     "Content-Type": "application/apply-patch+yaml"})
        _check(r)

    def get_json(self, path: str, params: dict | None = None) -> dict | None:
        """GET an API path; None on 404."""
        r = self._http.get(path, params=params or {}, headers=self._auth())
        if r.status_code == 404:
            return None
        _check(r)
        return r.json()

    def list_names(self, api_version: str, kind: str, namespace: str,
                   label_selector: str) -> list[str]:
        r = self._http.get(_path(api_version, kind, namespace),
                           params={"labelSelector": label_selector},
                           headers=self._auth())
        _check(r)
        return [i["metadata"]["name"] for i in r.json().get("items", [])]

    def delete(self, api_version: str, kind: str, namespace: str,
               name: str) -> None:
        r = self._http.delete(f"{_path(api_version, kind, namespace)}/{name}",
                              headers=self._auth())
        if r.status_code != 404:
            _check(r)

    def list_pod_ips(self, namespace: str, label_selector: str,
                     timeout: float = 10) -> set[str]:
        """IPs of Running pods, excluding hostNetwork pods (podIP == hostIP: the node's
        address, shared with everything else on that node, never identifies the pod)."""
        r = self._http.get(_path("v1", "Pod", namespace),
                           params={"labelSelector": label_selector},
                           headers=self._auth(), timeout=timeout)
        _check(r)
        return {i["status"]["podIP"] for i in r.json().get("items", [])
                if i.get("status", {}).get("phase") == "Running"
                and i["status"].get("podIP")
                and i["status"]["podIP"] != i["status"].get("hostIP")}


_client: K8sClient | None = None
_client_lock = threading.Lock()


def incluster_client() -> K8sClient:
    """The process-wide in-cluster client, built on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = K8sClient.from_incluster()
        return _client
