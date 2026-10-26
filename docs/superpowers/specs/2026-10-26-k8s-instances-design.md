# k8s phase 2: instances on Kubernetes — design

## Intent
On the k8s deployment (`ROUTE_BACKEND=k8s`, no Docker socket) users launch, stop, start,
restart and delete template instances exactly as on compose. Same UI, same API, same routes
(`/i/<subdomain>`). Instances must not become a way into the cluster or the LAN.

## Goals
- Template instance → Deployment (replicas 0/1) + Service + PVCs in namespace `styx-instances`.
- Lifecycle parity: launch, start, stop (idle monitor too), restart, delete (+ volumes), status.
- Routes: existing IngressRoute builder, upstream `selkies-<sub>.styx-instances.svc:<port>`
  (phase 1 already maps `<svc>.<ns>.svc` to a cross-namespace Traefik ref).
- GPU templates get `amd.com/gpu: <gpu_count>` (device plugin exposes /dev/dri).

## Non-goals (this phase)
- Image management page (pull/remove/list): kubelet pulls; endpoints return empty/no-op on k8s.
- Screenshots, stats graphs (phase 4 "small bits").
- DinD and privileged templates: refused on k8s with a clear 422 ("not supported on Kubernetes").

## Anti-goals
- Instance pods with a ServiceAccount token, hostPath, hostNetwork, privileged, or any route to
  the k8s API, node IPs, LAN, or other namespaces' pods.
- Backend RBAC beyond the `styx-instances` namespace for instance objects.

## Security model (decided earlier with the owner, recorded in memory `matrix-card-2fa`)
- Namespace `styx-instances`, PSA `enforce: baseline`, `warn: restricted`.
- Pod: `automountServiceAccountToken: false`, `enableServiceLinks: false`, seccomp RuntimeDefault,
  `allowPrivilegeEscalation: false`, caps drop ALL + template `cap_add` (baseline-allowed only;
  others rejected 422 on k8s).
- Backend Role in `styx-instances`: deployments, services, PVCs, pods (get/list), pods/log —
  nothing cluster-wide.
- ResourceQuota + LimitRange in the namespace (defaults: requests from template limits).
- CiliumNetworkPolicy:
  - ingress: only from namespace `traefik`.
  - egress: kube-dns (UDP/TCP 53) allowed; `world` allowed EXCEPT RFC1918, CGNAT 100.64/10,
    link-local, and the cluster/pod/service CIDRs; the LAN `192.168.1.0/24` IS allowed by default
    (owner: "Internet + LAN"), minus node IPs (192.168.1.83/84/85/206 — make this `INSTANCE_EGRESS_DENY_CIDRS`) and the k8s API; plus an admin allowlist of CIDRs
    (`INSTANCE_EGRESS_ALLOW_CIDRS`, global) and of named services (`ns/name`, via `toServices`).
  - Per-template allowlist: deferred to a later phase (global only now). *Builder's call → owner may change.*
- Instances of different owners cannot reach each other (ingress only from traefik covers it).

## Mapping (DockerManager method → k8s)
| Docker | k8s (`K8sInstanceRuntime`, same method names) |
|---|---|
| `image_exists` | always True (kubelet pulls) |
| `pull_image_streaming` | no-op |
| `get_image_info` | `{"id": image, "size": 0}`-style stub (check PulledImage fields) |
| `create_volume(name)` | PVC `name`, storageClass `INSTANCE_STORAGE_CLASS` (default `longhorn`), size `INSTANCE_VOLUME_SIZE` (default `20Gi`) |
| `remove_volume` | delete PVC |
| `ensure_user_network(owner)` | returns owner id (used as pod label `styx/owner`) |
| `ensure_isolated` | no-op (policy is namespace-wide) |
| `create_container(...)` | apply Deployment `selkies-<sub>` (replicas 0) + Service `selkies-<sub>`; returns name as container_id |
| `start/stop/restart_container` | scale 1 / scale 0 / rollout restart annotation |
| `pause/unpause` | 422 not supported on k8s |
| `remove_container` | delete Deployment + Service |
| `get_container_status` | from Deployment + pod phase → same dict shape as Docker version |

Template field mapping: env → env; memory/cpu limit → limits (+ requests = 25% cpu, 50% mem);
shm_size → emptyDir Memory at /dev/shm; tmpfs → emptyDir Memory; read_only_rootfs →
`readOnlyRootFilesystem`; entrypoint/command → command/args; extra_hosts → hostAliases (IPs must
pass the egress rules anyway); ulimits, devices, security_opt, extra_docker_args → ignored on k8s
with a warning log (devices other than GPU are not allowed). restart_policy: Deployment always
restarts; stop = scale 0.

## Images
Local-only image names (no `/`, e.g. `selkies-desktop:latest`) map to `K8S_DESKTOP_IMAGE`
(default `ghcr.io/sgtslaughta/styx-desktop:latest`). The package is public (owner): no pull secret.

## Selection
`container_runtime()` (phase 1 factory) gains an instance variant used by `routers/instances.py`,
`session_monitor.py`, `main.py` startup reconcile. Compose path unchanged.

## Left to the builder
File layout (keep each < 500 lines), exact status mapping, test shape (fake client, as phase 1).
