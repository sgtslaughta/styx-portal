# Kubernetes (k3s)

You will run Styx on Kubernetes with the Kustomize manifests in `deploy/k8s/`. This
targets a k3s cluster with Traefik, Cloudflare Tunnel (`cloudflared`), Longhorn
and (optionally) kube-prometheus-stack.

## Prerequisites

- k3s 1.34+ with a CNI that enforces `NetworkPolicy` (Cilium).
- Traefik in namespace `traefik` (IngressRoute CRDs under `traefik.io`).
- Longhorn (`driver.longhorn.io`) for the data and backup volumes.
- `cloudflared` pods in namespace `cloudflared` labelled `pod=cloudflared`.
- kube-prometheus-stack in `monitoring` (for the alert rules; the `PrometheusRule` CRD must exist).

Edit `deploy/k8s/configmap.yaml` first (`DOMAIN`, `TRUSTED_PROXY_CIDRS` = your
pod CIDR, `WORKSTATION_ALLOW_CIDRS` = your LAN) and set the image tag in
`deploy/k8s/kustomization.yaml` (`images:` block) to the release you deploy.
The tag must be **>= v2.3.0** (the manifests currently pin `2.7.0`), the first release with `ROUTE_BACKEND=k8s`; older
tags boot healthy but publish no IngressRoutes, so every route returns 404.
After boot, check `kubectl -n styx get ingressroutes` (expect the Styx base routes).

## Topology

![Kubernetes deployment layout by namespace: edge tunnel, Traefik, portal and instances](../assets/diagrams/operate-kubernetes-1-light.svg#only-light)
![Kubernetes deployment layout by namespace: edge tunnel, Traefik, portal and instances](../assets/diagrams/operate-kubernetes-1-dark.svg#only-dark)

## Install

`JWT_SECRET` must be the one your portal already uses. The Fernet key that
encrypts stored OAuth client secrets is derived from it, so a fresh random
value makes migrated SSO providers unreadable. Take it from the compose
`.env`, or from `jwt_secret` in compose's `/app/data/secrets.json`. Only for a
brand-new portal with nothing to migrate, generate one with `openssl rand -base64 48`.

```bash
kubectl apply -f deploy/k8s/namespace.yaml

# Secrets are created by hand and never committed. See secrets.example.env.
kubectl -n styx create secret generic styx-secrets \
  --from-literal=JWT_SECRET='<the compose JWT_SECRET>'

kubectl apply -k deploy/k8s
kubectl -n styx rollout status deploy/backend deploy/frontend
```

Preview first with `kubectl apply -k deploy/k8s --dry-run=server` (the
namespace must already exist).

## Data migration from compose

Copy what the backend needs at runtime from the compose data dir into the
`styx-data` volume: `styx-portal.db`, `secrets.json` (if present) and
`artifacts/` (agent tarballs, about 510M). Skip `screenshots/`, `lan-certs/`
and `*.pre-*` backups.

```bash
# 1. On the compose host: stage a consistent DB copy + needed files, tar them.
docker compose exec -T backend python - <<'PY'
import os, shutil, sqlite3, tarfile
os.makedirs('/tmp/stage', exist_ok=True)
d = sqlite3.connect('/tmp/stage/styx-portal.db')
sqlite3.connect('/app/data/styx-portal.db').backup(d)
print('integrity:', d.execute('PRAGMA integrity_check').fetchone()[0])
d.close()
if os.path.exists('/app/data/secrets.json'):
    shutil.copy('/app/data/secrets.json', '/tmp/stage/')
shutil.copytree('/app/data/artifacts', '/tmp/stage/artifacts', dirs_exist_ok=True)
with tarfile.open('/tmp/styx-data.tar', 'w') as t:
    for n in os.listdir('/tmp/stage'):
        t.add('/tmp/stage/' + n, arcname=n)
PY
docker compose cp backend:/tmp/styx-data.tar ./styx-data.tar
docker compose exec backend rm -rf /tmp/stage /tmp/styx-data.tar

# 2. Stop the k8s backend and start a restore pod (busybox, uid 1000) on the volume.
kubectl -n styx scale deploy/backend --replicas=0
kubectl -n styx run restore --restart=Never --image=busybox:1.37 --overrides='{"spec":{"securityContext":{"runAsUser":1000,"runAsGroup":1000,"fsGroup":1000},"containers":[{"name":"restore","image":"busybox:1.37","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/app/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"styx-data"}}]}}'
kubectl -n styx wait --for=condition=Ready pod/restore

# 3. Copy and unpack (files end up owned by 1000 through the pod uid/fsGroup).
kubectl -n styx cp styx-data.tar restore:/tmp/styx-data.tar
kubectl -n styx exec restore -- sh -c 'tar xf /tmp/styx-data.tar -C /app/data && rm /tmp/styx-data.tar && chown -R 1000:1000 /app/data && ls -la /app/data'

# 4. Clean up and start the backend.
kubectl -n styx delete pod restore
kubectl -n styx scale deploy/backend --replicas=1
```

If the tar layout looks wrong, check `ls /app/data` in the restore pod: you want
`styx-portal.db`, `secrets.json` and `artifacts/` at the top level.

OAuth providers migrated from another hostname keep their old redirect URIs.
Add `https://styx.example.com/...` to each identity provider or SSO fails after cutover.

## Cloudflare cutover

In the Cloudflare Zero Trust dashboard, add a public hostname to the tunnel:

- Hostname: `styx.example.com`
- Service: `https://traefik.traefik.svc.cluster.local:443`
- Additional settings: **No TLS Verify** on, **Origin Server Name** `styx.example.com`

A compose deployment on another hostname (e.g. `compose.example.com`) can keep running alongside.

## Agent enrollment

Workstations enroll against the public URL (`https://styx.example.com`). Existing
workstations that enrolled against another hostname must be re-enrolled
(generate a new enrollment command in the UI and re-run it).

## What works on Kubernetes

`ROUTE_BACKEND=k8s` publishes workstation, service and instance routes as Traefik `IngressRoute`s. There is no Docker socket (`DOCKER_SOCKET` points nowhere), so the Docker features have Kubernetes equivalents:

| Feature | On Kubernetes |
|---|---|
| Workstations | Same as Compose |
| Proxied services | Cluster Services and hostnames (ExternalName); discovery and health come from the Kubernetes API. Cross-namespace routes into system namespaces are denied (`K8S_UPSTREAM_DENY_NAMESPACES`) |
| Desktop instances | Run as Deployments with a Service and PVC in the `styx-instances` namespace (`K8S_INSTANCE_NAMESPACE`), image `K8S_DESKTOP_IMAGE`, storage class `INSTANCE_STORAGE_CLASS`, volume size `INSTANCE_VOLUME_SIZE` / `PROFILE_VOLUME_SIZE`. Namespace has RBAC, quota and a network policy (`deploy/k8s/instances.yaml`) |
| Managed mounts | Not applied automatically; the panel shows **manual** base-path instructions instead. The managed apply API answers 422 |
| Diagnostics | Kubernetes checks and setup preflight |
| Template editor | Docker-only fields (Security, restart policy, extra Docker args) are hidden |
| Instance usage | From metrics-server |

Templates that need Docker-in-Docker, privileged mode or extra capabilities are refused with a 422. That includes the bundled Developer Workstation template (Docker-in-Docker).

Proxied services cannot point at these namespaces by default (`K8S_UPSTREAM_DENY_NAMESPACES`): `kube-system`, `kube-public`, `kube-node-lease`, `default`, `longhorn-system`, `cert-manager`, `metallb-system`, `argocd`.

## Reliability

- Backend: 1 replica, `Recreate` strategy (RWO volume + SQLite allow one writer).
  Startup probe allows 150s to boot; liveness is deliberately slow (6 failures x 20s) so a busy backend is never killed.
- Node loss: `not-ready`/`unreachable` tolerations of 30s evict the pod about 30s after the node is declared lost, but that does not mean the replacement starts in 30s. The Longhorn setting `node-down-pod-deletion-policy` is `delete-both-statefulset-and-deployment-pod` (live), so Longhorn force-deletes pods on a down node and the `Recreate` backend reschedules after the 30s toleration plus the Longhorn detach, instead of waiting about 6 minutes on Multi-Attach. This is a shared cluster setting; these manifests do not change it.
- Backend prefers to avoid the single control-plane node (soft anti-affinity).
- Frontend: 2 replicas spread across nodes, PodDisruptionBudget `minAvailable: 1`.
- Both use PriorityClass `styx-critical` so they preempt ordinary workloads under pressure.
- Storage: StorageClass `longhorn-styx` keeps 3 replicas, `Retain`: deleting a PVC never deletes the volume.
- Alerts (`prometheusrule.yaml`): `StyxBackendDown` (critical), `StyxBackupFailed`, `StyxBackupStale`. `StyxBackupStale` also fires while no backup has ever succeeded, which is expected right after install until the first run completes.

## Backup & restore

CronJob `styx-db-backup` runs daily at 03:17 on the backend's node, using the
backend image (no extra images or credentials). It writes to the `styx-backups`
volume: a consistent SQLite copy `styx-portal-YYYY-MM-DD.db` (read-only source,
`PRAGMA integrity_check` must return `ok` or the job fails) and
`secrets-YYYY-MM-DD.json` if `secrets.json` exists. Files older than 14 days
are deleted. The job has a 30 minute deadline.

Run one on demand and list results:

```bash
kubectl -n styx create job --from=cronjob/styx-db-backup backup-now
kubectl -n styx logs job/backup-now
```

The backup volume lives in the same Longhorn cluster as the data. Periodically
copy it off-cluster (for example `kubectl cp` from a pod mounting `styx-backups`).

Restore (backend stopped, then copy a dump over the DB using the restore pod
from the migration section). The pod's `--overrides` JSON must also mount the
`styx-backups` PVC: add `{"name":"b","persistentVolumeClaim":{"claimName":"styx-backups"}}`
to `volumes` and `{"name":"b","mountPath":"/backups"}` to `volumeMounts`.
The backend image has no `sqlite3` CLI; use Python (busybox has neither, so run
this in a pod from the backend image, or on a copied file):

```bash
python -c "import sqlite3,sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))" SRC.db DST.db
```

```bash
kubectl -n styx scale deploy/backend --replicas=0
# in a restore pod: cp /backups/styx-portal-YYYY-MM-DD.db /app/data/styx-portal.db
kubectl -n styx scale deploy/backend --replicas=1
```

Also keep a copy of `JWT_SECRET` outside the cluster.

## Fallback access

Styx must not be your only remote path. If the tunnel, the cluster or Styx
itself is down, you need another way in:

- Run Tailscale or WireGuard on the workstations (and ideally a cluster node) so you can always reach them directly.
- Keep the compose stack stopped but intact as a cold standby (volumes, `.env`, tunnel token).

Failover to compose:

1. In Cloudflare Zero Trust, edit the tunnel public hostname for your portal
   host and point it at the compose Traefik, or re-add the compose hostname (for
   example `compose.example.com`) if you removed it.
2. On the compose host: `docker compose up -d`.
3. Restore the latest DB backup into the compose `backend` volume if its data is stale.
4. Re-enroll workstations if they were enrolled against the k8s hostname.
