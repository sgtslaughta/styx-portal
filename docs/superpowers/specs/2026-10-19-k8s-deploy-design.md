# Styx on Kubernetes (k3s) — Design

Date: 2026-10-19 · Branch: `feat/k8s-deploy` · Status: draft

## Intent

The owner upgraded this workstation (EliteMini, `192.168.1.196`, Ubuntu 26.04) and Kasm stopped working on it. They are moving fully to Styx. Today the Styx **server** runs on this same box under docker compose. The goal is to move the server into the home k3s cluster and leave this box running **only the agent**. The cluster replaces the compose host.

**MVP success:** open `https://s.jmolabs.dev`, log in with the existing account, and stream this workstation through the agent, with the server running in the cluster.

## Goals

- Run Styx k8s-native: the **existing cluster Traefik** (`traefik` ns, LB `192.168.1.240`, v3.6.2) serves all Styx traffic. No bundled Traefik pod.
- The backend publishes routes as **Traefik CRDs** through the k8s API, replacing file-provider output in k8s mode.
- Outside access goes through the **existing cluster cloudflared** (`cloudflared` ns, dashboard-managed tunnel, `tunnelToken` secret). No tunnel pod ships with Styx.
- **All client traffic goes through Cloudflare** (owner decision "A"), including the agent's enrollment and heartbeat. No LAN shortcut, no self-signed LAN cert, no pinned CA in k8s mode.
- Manifests are Kustomize in the repo (`deploy/k8s/`) and applied with `kubectl apply -k` (owner decision; ArgoCD maybe later).
- Migrate the existing SQLite DB (3 users) so accounts carry over.
- The compose deploy keeps working unchanged (k8s mode is opt-in).

## Non-goals (MVP)

- Container instances (Kasm-style). The cluster runs containerd and has no Docker socket. Instance features may error or be hidden; they must not crash the backend. Instances may later become pods, which is a separate project.
- Proxied services (SP1) and the `styxlocation` Traefik plugin. That would mean installing a plugin into shared cluster Traefik. Deferred.
- ArgoCD, Helm, HA/multiple replicas, Postgres.
- Fixing unrelated cluster issues: one crashlooping cloudflared replica, the stuck `kasm` namespace, the gitlab-runner crashloop. These are noted, not touched.

## Anti-goals

- Weakening the client-IP trust boundary. If any LAN pod or host can forge `CF-Connecting-IP`/`X-Forwarded-For` and get around login bans or lockout, that is a failure.
- Cluster-wide RBAC for the backend. Its ServiceAccount must be limited to the `styx` namespace.
- Changing shared cluster components (cluster Traefik args, cloudflared) beyond what the owner does by hand in the Cloudflare dashboard.
- Committing secrets.

## Cluster facts (recon 2026-10-19)

- k3s v1.34.2, 4 nodes (k1-n1 uncordoned today), containerd, Cilium, pod CIDR `10.42.0.0/16`.
- Storage: `longhorn` (RWO, expandable) and `local-path`.
- Traefik providers: `kubernetescrd` (allowCrossNamespace=true) and `kubernetesingress`. Entrypoints `web` (:8000) and `websecure` (:8443, TLS on). `web` redirects to https by default (`traefik-https-redirect@kubernetescrd`). `serversTransport.insecureSkipVerify=true` globally.
- cert-manager with `letsencrypt-production`/`-staging` ClusterIssuers (not needed: Cloudflare terminates public TLS).
- MetalLB L2 `default-pool`; AdGuard serves LAN DNS on `.241`.

## Decided design

### Workloads (`styx` namespace)

- **backend** Deployment: 1 replica, `strategy: Recreate` (SQLite on an RWO volume), image `ghcr.io/sgtslaughta/styx-backend:<tag>`, runs as uid 1000 with `fsGroup: 1000` (replaces compose's `volume-init` chown). PVC `styx-data` on Longhorn at `/app/data`. Readiness and liveness on `/api/health`.
- **frontend** Deployment: image `ghcr.io/sgtslaughta/styx-frontend:<tag>`, port 3000.
- Services `backend` (8000) and `frontend` (3000). The backend's existing internal URLs (`http://backend:8000/...` forwardAuth) must resolve from **cluster Traefik's** namespace, so CRDs must reference the backend by FQDN (`backend.styx.svc.cluster.local`) or by k8s Service object rather than by bare `backend`.
- Templates and agent files: compose bind-mounts `./templates` and `./agent`. In k8s, the backend image must contain both. The enrollment script and agent download come from `/app/agent`. Builder choice: bake them into the image, or ship a ConfigMap if they are small enough.
- `/dev/dri` and GPU group_add: dropped (only used for instance screenshots/GPU detection).

### Config

- ConfigMap: `DOMAIN=s.jmolabs.dev`, `DEPLOY_MODE=tunnel`, `COOKIE_SECURE=true`, `DATABASE_URL=sqlite+aiosqlite:///./data/styx-portal.db`, plus the new `ROUTE_BACKEND=k8s`, the target namespace, and the trust CIDRs (below).
- Secret `styx-secrets`, made by hand from the current `.env` (`JWT_SECRET` and any other secret keys). The repo ships `deploy/k8s/secrets.example.env` with blank values only. **`JWT_SECRET` must match the old value**, or the Fernet-encrypted OAuth provider secrets (key = HKDF(JWT_SECRET)) and existing sessions break.
- Note: the live `.env` points `DATABASE_URL` at the stale `selkies-hub.db`, while compose overrides it to `styx-portal.db`. Migrate **`styx-portal.db`** (the file the running backend uses; confirm via `docker exec`).

### Routing: `ROUTE_BACKEND=k8s`

- `build_routes_config()` stays the single source of route truth. A new k8s writer turns its dict into:
  - `IngressRoute` (traefik.io/v1alpha1) per router, on entrypoint `websecure` (cloudflared's existing convention is `https://traefik.traefik.svc.cluster.local:443`; Styx's hostname uses the same). `Host()`/path rules and priorities kept.
  - `Middleware` per middleware (stripPrefix, headers, forwardAuth, ratelimit, errors, and the ip-ban-gate equivalent).
  - Upstreams: in-cluster ones (`api`, `frontend`) map to the k8s Services. **Workstation upstreams** (`http(s)://<lan_ip>:<port>`) map to a selector-less `Service` plus an `EndpointSlice` (or `Endpoints`) in `styx` pointing at the workstation LAN IP and port. `https` workstations need a `ServersTransport` CRD with insecureSkipVerify (mirrors `selkies-transport`).
- Every object labeled `app.kubernetes.io/managed-by=styx-backend`. Each refresh applies the desired set (server-side apply) and **deletes managed objects that are no longer desired**. Writes are idempotent. `strict` refresh semantics carry over (errors surface the same way the file writer's do).
- LAN routers (`*-lan`) and `tls` LAN-cert blocks are skipped in k8s mode (decision A).
- Proxied-service routes: skipped in k8s mode for MVP (non-goal). The UI may still list services, but no routes get emitted.
- RBAC: ServiceAccount `styx-backend`, a Role in `styx` allowing get/list/watch/create/update/patch/delete on `ingressroutes`, `middlewares`, `serverstransports` (traefik.io), `services`, `endpointslices`/`endpoints`. Nothing cluster-scoped.
- Static routes that compose's `traefik/dynamic.yml` provides (api, frontend, error pages, ratelimit, ip-ban-gate) are **emitted by the writer** along with the workstation objects, translated from the same `build_routes_config()` dict (designer's call, revised during planning: one source of truth, and ratelimit stays live-tunable from Settings). `deploy/k8s/` ships no IngressRoutes.

### Client-IP trust boundary (security-critical)

Request path: browser → Cloudflare → cloudflared pod → cluster Traefik pod → backend pod.

- Today the backend believes `CF-Connecting-IP` only when the peer Traefik saw is in `TUNNEL_PEER_CIDRS` (the compose tunnel subnet), and believes `X-Forwarded-For` only from `TRUSTED_PROXY_CIDRS`.
- In k8s, cloudflared and Traefik pod IPs change within `10.42.0.0/16`. The pod CIDR alone is **not** a boundary, since any pod can reach Traefik's pod and the backend directly.
- Required:
  1. **NetworkPolicy** (Cilium enforces it): backend ingress allowed only from cluster-Traefik pods (traefik ns) on 8000. Frontend the same on 3000.
  2. Backend trusts forwarded headers only from the Traefik pod range it can see. Traefik must pass the **cloudflared peer** in a header the backend can trust, or Traefik's `forwardedHeaders.trustedIPs` must be limited to cloudflared. Either way, the builder must prove that a request reaching Traefik from a non-cloudflared source (LAN host hitting `192.168.1.240` directly, or another pod) cannot set the client IP the backend uses for bans and lockout.
  3. A test or documented manual check showing a forged `CF-Connecting-IP` from the LAN gets ignored.
- Note: cluster Traefik's LB `.240` is reachable from the LAN, so LAN clients can hit Styx routes directly without Cloudflare. That is allowed (same Host rule) as long as (2) holds.

### Agent on this machine

- Re-enroll the EliteMini agent against `https://s.jmolabs.dev` (no `SERVER_LAN_URL`, no CA pin). Server-to-agent stream traffic: cluster Traefik pod → `192.168.1.196:<agent port>` over LAN. The builder verifies that Cilium egress/masquerade allows pod → LAN host, and that the host firewall on the EliteMini allows the cluster node IPs (`192.168.1.83–85, .206`).
- Agent must not need a toolchain installed on the box (standing rule). Use existing prebuilt artifacts. Ubuntu 26.04 compatibility of the agent is **in scope only if it blocks MVP**.

### Cutover

1. Back up the live DB (`styx-portal.db`) from the compose backend (sqlite `.backup`, integrity check).
2. `kubectl apply -k deploy/k8s` with backend scaled to 0. Create `styx-secrets` by hand.
3. Copy the DB into PVC `styx-data` (helper pod or `kubectl cp` to a scaled-down pod), uid 1000.
4. Scale up. Test on the LAN with the real domain and no Cloudflare: `curl --resolve s.jmolabs.dev:443:192.168.1.240 -k` (or an `/etc/hosts` line for a browser). This checks login and the UI. No temporary hostname and no code needed (designer's call). Agent streaming gets tested after step 5.
5. Owner moves `s.jmolabs.dev` in the Cloudflare dashboard from the compose tunnel to the cluster tunnel, with service `https://traefik.traefik.svc.cluster.local:443` (noTLSVerify, as for the existing Traefik-routed hostnames).
6. `docker compose stop` on the EliteMini. **Do not delete** volumes or the stack.
7. Re-enroll or re-point the agent. Verify streaming.
8. Rollback: point the hostname back to the compose tunnel and `docker compose start`.

### Versioning

Semantic commits. Release as a minor bump (new deploy target). Images come from the existing tag pipeline to GHCR.

## Left to the builder

- k8s client: the `kubernetes` Python package vs. raw `httpx` against the in-cluster API (ServiceAccount token). Prefer whichever is smaller and testable with mocks.
- The exact mapping from file-provider dict → CRD specs, and object naming (DNS-1123 safe, ≤63 chars).
- How the backend runs with no Docker: make sure instance and screenshot loops degrade quietly (boot already tolerates no Docker).
- Static vs. emitted base routes (api, frontend, errors, ratelimit).
- Tests: unit tests for the dict→CRD translation and the prune logic, with a mocked API. NetworkPolicy and trust check as a documented manual or e2e step.
- Docs page `docs/` for the k8s deploy (Zensical site).
- CI must stay green (GitHub + GitLab parity pipelines).

## Trust boundary: recon facts and required proof

- Cluster Traefik has no `forwardedHeaders.trustedIPs`. It overwrites `X-Forwarded-For` with the peer it saw and passes `CF-Connecting-IP` through unchanged, so that header is client-forgeable at Traefik.
- Traefik LB service is `externalTrafficPolicy: Cluster`. LAN clients hitting `192.168.1.240` may show up at Traefik SNAT'd (node IP `192.168.1.83–85/.206`, or a Cilium host IP inside `10.42.0.0/16`). Cloudflared shows up as its pod IP in `10.42.0.0/16`.
- **Builder's first task, before writing trust code:** deploy a throwaway whoami behind cluster Traefik. Record the XFF Traefik sets for (a) a request through the tunnel and (b) a LAN request from `192.168.1.196` straight to `.240`. Trust is designed from that evidence:
  - If LAN sources never land in the cloudflared pod range: trust `CF-Connecting-IP` only when Traefik's XFF peer is a cloudflared pod. Cloudflared pod IPs are discoverable via the API (label selector, read-only `pods` list in the `cloudflared` ns: this adds one narrow cross-namespace Role) or via a configured CIDR.
  - If they can collide (Cilium SNAT into `10.42.x`): escalate to the owner. Do not ship. Options then: `externalTrafficPolicy: Local` on cluster Traefik (shared-component change, owner's call) or a Styx-only path from cloudflared.
- The proof in the "Client-IP trust boundary" section (forged `CF-Connecting-IP` from the LAN is ignored) is the acceptance gate.
