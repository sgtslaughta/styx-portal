# k8s phase 1: service discovery + health

Goal: on `ROUTE_BACKEND=k8s` (no Docker socket), "docker-local" proxied services work against
cluster Services: discover, attach, route, health, favicon. Compose mode unchanged.

Design (decided):
- A k8s Service is named in the existing `ProxiedService.container` field as `<svc>.<ns>.svc`
  (resolves in cluster DNS). `upstream_base()` then yields `http://<svc>.<ns>.svc:<port>`, unchanged.
- `K8sRuntime` duck-types the DockerManager methods services use. One factory picks it.
- Traefik already runs with `allowCrossNamespace=true`: route to `{name: svc, namespace: ns, port}`.

## Task 1 — K8sClient read helpers (`backend/app/services/k8s_api.py`)
Add to `K8sClient`:
```python
def get_json(self, path: str, params: dict | None = None) -> dict | None:
    """GET an API path; None on 404."""
    r = self._http.get(path, params=params or {}, headers=self._auth())
    if r.status_code == 404:
        return None
    _check(r)
    return r.json()
```
Test with an `httpx.MockTransport` (see existing tests in `tests/test_k8s_sync.py` for how a
client is built with a transport): 200 returns dict, 404 returns None, 500 raises.

## Task 2 — `backend/app/services/k8s_runtime.py` (new, < 120 lines)
```python
SKIP_NS = {"kube-system", "kube-public", "kube-node-lease"}  # plus Settings().K8S_NAMESPACE

class K8sRuntime:
    def __init__(self, client=None): self._c = client or incluster_client()
    def list_containers(self) -> list[dict]
    def container_health(self, name: str) -> str
    def ensure_traefik_network(self, name: str) -> None: pass
    def connect_to_network(self, container: str, network: str) -> bool: return True
    def disconnect_from_network(self, container: str, network: str) -> None: pass
```
- `list_containers`: GET `/api/v1/services`. Skip SKIP_NS, the styx namespace
  (`Settings().K8S_NAMESPACE`; grep config.py for the existing namespace setting name and use it),
  services with no ports, and `type: ExternalName`. Return
  `{"name": f"{name}.{ns}.svc", "image": <selector "app.kubernetes.io/name" or "app" label value, else "">,
  "ports": sorted TCP ports, "networks": [ns]}`.
- `container_health(name)`: parse `svc.ns.svc` (anything else -> "unknown"). GET
  `/apis/discovery.k8s.io/v1/namespaces/{ns}/endpointslices` with
  `labelSelector=kubernetes.io/service-name={svc}`. Any endpoint with `conditions.ready` true ->
  "healthy"; slices exist but none ready -> "unhealthy"; Service itself 404 -> "unhealthy";
  any exception -> "unknown".
- Tests `tests/test_k8s_runtime.py` with a fake client exposing `get_json(path, params)`:
  list filters + shape; health healthy/unhealthy/missing/bad-name/exception.

## Task 3 — factory
In `backend/app/services/k8s_runtime.py`:
```python
def container_runtime():
    if Settings().ROUTE_BACKEND == "k8s":
        return K8sRuntime()
    from app.services.docker_manager import DockerManager
    return DockerManager(network_name=Settings().DOCKER_NETWORK)
```
Use it in: `routers/services.py:get_docker_manager`, `services/service_health.py:_default_docker`.
Nothing else yet.

## Task 4 — routes (`backend/app/services/k8s_routes.py:_service_objects`)
In the non-IP branch, before `ref = {"name": host, ...}`: if host matches
`^([a-z0-9-]+)\.([a-z0-9-]+)\.svc(\.cluster\.local)?$` ->
`ref = {"name": m[1], "namespace": m[2], "port": port}`. Test in `tests/test_k8s_routes.py`:
a docker-local service with container `sonarr.media.svc`, port 8989, produces an IngressRoute
service ref `{"name": "sonarr", "namespace": "media", "port": 8989}` and no extra Service object.
(Build the config the way existing service tests do: grep `build_routes_config` + `services=`.)

## Task 5 — favicon (`backend/app/services/service_favicon.py:_getter`)
Change `if svc.kind == "docker-local":` to
`if svc.kind == "docker-local" and Settings().ROUTE_BACKEND != "k8s":` (k8s: backend fetches
over httpx directly). Test: with ROUTE_BACKEND=k8s monkeypatched, a docker-local svc uses the
httpx path (use the existing transport-injection pattern in `tests/test_service_favicon.py`).

## Task 6 — RBAC (`deploy/k8s/rbac.yaml`)
Append a ClusterRole `styx-backend-discovery` (rules: core `services` get/list; `discovery.k8s.io`
`endpointslices` get/list) + ClusterRoleBinding to SA `styx-backend` in ns `styx`.
Comment: "read-only: service discovery + health for docker-local services".

## Gate
`cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
All green. One commit per task, semantic (`feat(k8s): ...`), trailer
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.
