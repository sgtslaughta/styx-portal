# Kubernetes (k3s)

Run Styx on Kubernetes with the Kustomize manifests in `deploy/k8s/`. This
targets a k3s cluster with Traefik, Cloudflare Tunnel (`cloudflared`), Longhorn
and (optionally) kube-prometheus-stack.

## Prerequisites

- k3s 1.34+ with a CNI that enforces `NetworkPolicy` (Cilium).
- Traefik in namespace `traefik` (IngressRoute CRDs under `traefik.io`).
- Longhorn (`driver.longhorn.io`) for the data volume.
- `cloudflared` pods in namespace `cloudflared` labelled `pod=cloudflared`.
- MinIO reachable at `minio.minio.svc.cluster.local:9000` with a `styx-backups` bucket (for backups).
- kube-prometheus-stack in `monitoring` (for the alert rules; the `PrometheusRule` CRD must exist).

Edit `deploy/k8s/configmap.yaml` first (`DOMAIN`, `TRUSTED_PROXY_CIDRS` = your
pod CIDR, `WORKSTATION_ALLOW_CIDRS` = your LAN) and set the image tag in
`deploy/k8s/kustomization.yaml` (`images:` block) to the release you deploy.

## Install

```bash
kubectl apply -f deploy/k8s/namespace.yaml

# Secrets are created by hand and never committed. See secrets.example.env.
kubectl -n styx create secret generic styx-secrets \
  --from-literal=JWT_SECRET="$(openssl rand -base64 48)"
kubectl -n styx create secret generic styx-backup-s3 \
  --from-literal=MC_HOST_local='http://ACCESS_KEY:SECRET_KEY@minio.minio.svc.cluster.local:9000'

# The backup bucket must exist before the first backup runs:
kubectl -n minio run mc --rm -it --restart=Never --image=minio/mc:RELEASE.2024-11-21T17-21-54Z \
  --env MC_HOST_local='http://ACCESS_KEY:SECRET_KEY@minio.minio.svc.cluster.local:9000' \
  --command -- mc mb --ignore-existing local/styx-backups

kubectl apply -k deploy/k8s
kubectl -n styx rollout status deploy/backend deploy/frontend
```

Preview first with `kubectl apply -k deploy/k8s --dry-run=server` (the
namespace must already exist).

## Database migration from compose

SQLite lives on the `styx-data` volume. To carry over an existing portal:

```bash
# on the compose host: consistent copy of the DB and secrets file
docker compose exec backend sqlite3 /app/data/styx-portal.db ".backup /app/data/migrate.db"
docker compose cp backend:/app/data/migrate.db ./styx-portal.db
docker compose cp backend:/app/data/secrets.json ./secrets.json   # only if you did not pin JWT_SECRET

# scale the backend down, copy into the volume, scale back up
kubectl -n styx scale deploy/backend --replicas=0
kubectl -n styx run restore --rm -it --restart=Never --image=busybox:1.37 \
  --overrides='{"spec":{"securityContext":{"runAsUser":1000,"fsGroup":1000},"containers":[{"name":"restore","image":"busybox:1.37","stdin":true,"tty":true,"command":["sh"],"volumeMounts":[{"name":"d","mountPath":"/app/data"}]}],"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"styx-data"}}]}}'
# in another terminal: kubectl -n styx cp styx-portal.db restore:/app/data/styx-portal.db
kubectl -n styx scale deploy/backend --replicas=1
```

Keep the same `JWT_SECRET` (or copy `secrets.json`); otherwise everyone is
logged out and stored OAuth client secrets become unreadable.

## Cloudflare cutover

In the Cloudflare Zero Trust dashboard, add a public hostname to the tunnel:

- Hostname: `g.jmolabs.dev`
- Service: `https://traefik.traefik.svc.cluster.local:443`
- Additional settings: **No TLS Verify** on, **Origin Server Name** `g.jmolabs.dev`

A compose deployment on another hostname (e.g. `s.jmolabs.dev`) can keep running alongside.

## Agent enrollment

Workstations enroll against the public URL (`https://g.jmolabs.dev`). Existing
workstations that enrolled against another hostname must be re-enrolled
(generate a new enrollment command in the UI and re-run it).

## Limits in Kubernetes mode

`ROUTE_BACKEND=k8s` publishes workstation and static routes as Traefik
`IngressRoute`s. There is no Docker socket, so **container instances and
proxied Docker services are unavailable**; only workstations and
non-Docker services work.

## Reliability

- Backend: 1 replica, `Recreate` strategy (RWO volume + SQLite allow one writer).
  Startup probe allows 150s to boot; liveness is deliberately slow (6 failures x 20s) so a busy backend is never killed.
- Node loss: `not-ready`/`unreachable` tolerations of 30s reschedule the pod in about 30s instead of the default 300s. Longhorn volume failover still applies.
- Backend prefers to avoid node `k1-n4` (the single control-plane node).
- Frontend: 2 replicas spread across nodes, PodDisruptionBudget `minAvailable: 1`.
- Both use PriorityClass `styx-critical` so they preempt ordinary workloads under pressure.
- Storage: StorageClass `longhorn-styx` keeps 3 replicas, `Retain`: deleting the PVC never deletes the volume.
- Alerts (`prometheusrule.yaml`): `StyxBackendDown` (critical), `StyxBackupFailed`, `StyxBackupStale`.

## Backup & restore

CronJob `styx-db-backup` runs daily at 03:17 on the backend's node. An
init container takes a consistent `sqlite3 .backup`, verifies
`PRAGMA integrity_check`, then `mc` uploads `styx-YYYY-MM-DD.db` to
`styx-backups` and deletes objects older than 14 days.

Run one on demand:

```bash
kubectl -n styx create job --from=cronjob/styx-db-backup backup-now
```

Restore (backend stopped, then copy the dump over the DB):

```bash
kubectl -n styx scale deploy/backend --replicas=0
# fetch styx-YYYY-MM-DD.db with mc, then copy into the volume as in "Database migration"
# remove any stale styx-portal.db-wal / -shm files in /app/data before starting
kubectl -n styx scale deploy/backend --replicas=1
```

Also keep a copy of `JWT_SECRET` (or `secrets.json`) outside the cluster.

## Fallback access

Styx must not be your only remote path. If the tunnel, the cluster or Styx
itself is down, you need another way in:

- Run Tailscale or WireGuard on the workstations (and ideally a cluster node) so you can always reach them directly.
- Keep the compose stack stopped but intact as a cold standby (volumes, `.env`, tunnel token).

Failover to compose:

1. In Cloudflare Zero Trust, edit the tunnel public hostname for your portal
   host and point it at the compose Traefik, or re-add the compose hostname (for
   example `s.jmolabs.dev`) if you removed it.
2. On the compose host: `docker compose up -d`.
3. Restore the latest DB backup into the compose `backend` volume if its data is stale.
4. Re-enroll workstations if they were enrolled against the k8s hostname.
