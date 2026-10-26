# k8s phase 2: instances — implementation plan

Design: `docs/superpowers/specs/2026-10-26-k8s-instances-design.md` (read it first).
Rule: on `ROUTE_BACKEND=k8s` instances run as Deployments in `styx-instances`; compose path
unchanged. Same method names as `DockerManager` so `routers/instances.py` barely changes.
TDD, one semantic commit per task, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
Gate: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`.

## Task 1 — manifests: `deploy/k8s/instances.yaml` (+ add to kustomization resources)
- Namespace `styx-instances`, labels `pod-security.kubernetes.io/enforce: baseline`,
  `pod-security.kubernetes.io/warn: restricted`.
- Role `styx-backend-instances` in `styx-instances`:
  apps `deployments` (get list watch create update patch delete),
  core `services`, `persistentvolumeclaims` (same verbs), core `pods` (get list), `pods/log` (get).
  RoleBinding to SA `styx-backend` ns `styx`.
- ResourceQuota `instances`: `requests.cpu: "16"`, `requests.memory: 48Gi`, `limits.cpu: "32"`,
  `limits.memory: 96Gi`, `persistentvolumeclaims: "40"`, `requests.storage: 800Gi`,
  `requests.amd.com/gpu: "3"`.
- LimitRange: container default limits `cpu: "2"`, `memory: 4Gi`; defaultRequest `cpu: 250m`, `memory: 512Mi`.
- CiliumNetworkPolicy `instances` (endpointSelector `{}`):
  - ingress: `fromEndpoints: [{matchLabels: {k8s:io.kubernetes.pod.namespace: traefik}}]`.
  - egress:
    1. `toEndpoints: [{matchLabels: {k8s:io.kubernetes.pod.namespace: kube-system, k8s-app: kube-dns}}]`,
       `toPorts: [{ports: [{port: "53", protocol: ANY}]}]`.
    2. `toCIDRSet: [{cidr: 0.0.0.0/0, except: [10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16,
       100.64.0.0/10, 169.254.0.0/16]}, {cidr: 192.168.1.0/24}]`.
    Comment: Cilium CIDR rules never select host/remote-node/kube-apiserver entities, so
    node IPs and the API stay blocked even inside 192.168.1.0/24.
- Test: `backend/tests/test_k8s_manifests.py` — yaml.safe_load_all the file; assert namespace
  labels, Role has no cluster-scoped kind, CNP ingress only traefik. (yaml is already a dep? check
  `pyproject.toml`; if not, skip this test and say so.)

## Task 2 — settings (`backend/app/config.py`)
```
K8S_INSTANCE_NAMESPACE: str = "styx-instances"
K8S_DESKTOP_IMAGE: str = "ghcr.io/sgtslaughta/styx-desktop:latest"
INSTANCE_STORAGE_CLASS: str = "longhorn"
INSTANCE_VOLUME_SIZE: str = "20Gi"
```

## Task 3 — K8sClient writes (`backend/app/services/k8s_api.py`)
Add `"Deployment": "deployments", "PersistentVolumeClaim": "persistentvolumeclaims"` to `_PLURALS`.
Add `patch_merge(api_version, kind, ns, name, body: dict)` (PATCH, content-type
`application/merge-patch+json`, `_check`) and `get_text(path, params) -> str | None` (404 -> None).
Tests with MockTransport like the existing ones.

## Task 4 — pure builder: `backend/app/services/k8s_instance_objects.py` (< 200 lines)
`build_objects(name, image, env, volumes, port, ns, owner, *, gpu_enabled, gpu_count,
memory_limit, cpu_limit, shm_size, cap_add, read_only_rootfs, tmpfs, extra_hosts, entrypoint,
command) -> list[dict]` returns [Deployment, Service]. Rules:
- image: no `/` in it -> `Settings().K8S_DESKTOP_IMAGE`.
- Deployment `name`, replicas 0, labels `{"app": name, "styx/owner": owner,
  "app.kubernetes.io/managed-by": "styx-backend"}`, strategy `Recreate` (RWO volumes).
- pod spec: `automountServiceAccountToken: False`, `enableServiceLinks: False`,
  `securityContext: {seccompProfile: {type: RuntimeDefault}}`.
- container: env list (add `PIXELFLUX_WAYLAND=true` default like docker), ports `[port]`,
  `securityContext: {allowPrivilegeEscalation: False, readOnlyRootFilesystem: read_only_rootfs,
  capabilities: {drop: ["ALL"], add: cap_add}}`.
- limits from memory_limit (`"8g"` -> `"8Gi"`, `"512m"` -> `"512Mi"`) / cpu_limit (`"4.0"` -> `"4"`);
  requests = cpu 25%, memory 50% of limit. gpu: `limits["amd.com/gpu"] = gpu_count`.
- volumes: `volumes` dict `{pvc_name: {"bind": mount}}` -> PVC volume + mount.
  shm_size -> emptyDir `{medium: Memory, sizeLimit}` at `/dev/shm`; each tmpfs path -> emptyDir Memory.
- extra_hosts -> hostAliases; entrypoint -> command; command -> args.
- Service `name`: selector `{"app": name}`, port `port` targetPort `port`, name `http`.
- `pvc(name, ns) -> dict`: RWO, storageClassName/size from settings, managed-by label.
- `refuse_reason(template) -> str | None`: "privileged"/"dind" or any cap in cap_add outside
  baseline set {AUDIT_WRITE, CHOWN, DAC_OVERRIDE, FOWNER, FSETID, KILL, MKNOD, NET_BIND_SERVICE,
  SETFCAP, SETGID, SETPCAP, SETUID, SYS_CHROOT} -> message; else None. NET_RAW is NOT baseline:
  drop it silently (log once) rather than refuse — templates list it by habit.
Tests: snapshot-ish asserts on each rule.

## Task 5 — runtime: `backend/app/services/k8s_instances.py` (< 250 lines)
`class K8sInstanceRuntime` (client injectable), methods with DockerManager names:
- `image_exists` -> True; `pull_image_streaming` -> None; `get_image_info(image)` -> `{"size_mb": 0, "id": image}`.
- `create_volume(name)` -> apply pvc (idempotent apply); `remove_volume(name)` -> delete PVC.
- `ensure_user_network(owner)` -> owner; `ensure_isolated(*a)`, `remove_user_network(*a)` -> None;
  `on_portal_network()` -> [].
- `create_container(name, image, labels, environment, volumes, port, network=..., **tmpl)`:
  apply `build_objects(...)` (owner = network arg); ignore labels/ulimits/devices/security_opt/
  extra_docker_args/restart_policy with one `logger.info`; return `name`.
- `start_container(n)` -> merge-patch `{"spec": {"replicas": 1}}`; `stop_container` -> replicas 0;
  `restart_container` -> patch template annotation `styx/restartedAt` = iso now;
  `pause_container`/`unpause_container` -> raise `NotImplementedError("pause is not supported on Kubernetes")`.
- `remove_container(n)` -> delete Deployment + Service.
- `get_container_status(n)`: Deployment 404 -> `{"status": "not_found"}`; `spec.replicas == 0` ->
  `"exited"`; `status.readyReplicas >= 1` -> `"running"` (+ `started_at` from the pod's
  `status.startTime` if easy, else ""); else `"created"`.
- `get_container_stats` -> {}; `container_logs(n, tail)` -> list[str] from
  `/api/v1/namespaces/{ns}/pods/{pod}/log?tailLines=&timestamps=true` for the pod with label `app=n`.
Tests with a fake client.

## Task 6 — wire in
- `k8s_runtime.py`: `def instance_runtime():` k8s -> `K8sInstanceRuntime()`, else DockerManager.
- `routers/instances.py:get_docker_manager` and `_launch_instance_background`'s
  `DockerManager(...)` -> `instance_runtime()`. `main.py` instance loops (`_run_monitor_pass`,
  `_reconcile_instances_at_boot`, metrics, `_log_portal_instances`) -> `instance_runtime()`.
  Leave screenshot service on Docker (phase 4) but make it no-op on k8s (skip the loop).
- Logs endpoint (instances.py ~line 902): move the Docker code into
  `DockerManager.container_logs(container_id, tail) -> list[str]` and call `docker.container_logs`.
- Launch/recreate: on k8s, if `refuse_reason(template)` -> HTTP 422 with that message
  (check before status changes).
- pause endpoint: catch NotImplementedError -> 422.
- route_writer: instance upstream host `selkies-<sub>` -> on k8s
  `selkies-<sub>.<K8S_INSTANCE_NAMESPACE>.svc` (phase 1 maps it to a cross-ns ref). Make sure the
  instance namespace is NOT in `denied_namespaces()`.
Tests: route_writer k8s instance ref; refuse -> 422; logs via fake runtime.

## Task 7 — templates
`templates/*.json`: no change (image mapping covers `selkies-desktop:latest`). Note in the plan
report which seeded templates are refused on k8s (dind / privileged).
