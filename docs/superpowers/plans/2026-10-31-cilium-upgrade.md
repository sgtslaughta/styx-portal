# Cilium upgrade 1.14.5 → 1.20.x (k3s homelab, 4 nodes) — plan (2026-10-31)

## Why

- 1.14.5 (Dec 2023) is EOL; upstream supports 1.18–1.20 only. The cluster runs k3s **v1.34**, years past what
  1.14 was tested against.
- 2026-10-30 19:15 EDT: a control-plane hiccup left every endpoint Cilium created on k1-n4 afterwards with
  `policy-enabled: both` and a deny-all BPF map (no rule selected them). DNS/API egress dropped as "Policy denied";
  `cilium endpoint regenerate` did not clear it, recreating the pods did. Affected Longhorn CSI/UI, authentik,
  cloudflared, gitlab-kas/runner, reflector, reloader, cert-manager-webhook, adguard-2.

## Current state (read before touching anything)

| Setting | Helm values (rev 23) | Live (ConfigMap / DaemonSet) |
|---|---|---|
| API server (`k8sServiceHost`) | `192.168.1.83` — **dead** (k1-n1 is no longer a server) | `192.168.1.206` (hand-patched in 4 places) |
| `kube-proxy-replacement` | `strict` | `partial` (hand-patched) |
| `bpf-lb-sock` | `false` | `true` |
| Routing | `tunnel: vxlan` (removed option) | `routing-mode=tunnel`, `tunnel-protocol=vxlan` |
| kube-proxy | — | DaemonSet **running** on all nodes |

Other: `ipam.mode=kubernetes` (PodCIDRs 10.42.{0..3}.0/24), Hubble + relay + UI on, `l7Proxy: true`, wireguard off,
operator 1 replica, `policyEnforcementMode: default`. Policies in use: Longhorn + styx + gitlab `NetworkPolicy`s,
one `CiliumNetworkPolicy` (`styx-instances/instances`).

> **Trap:** `helm upgrade --reuse-values` re-applies `k8sServiceHost=192.168.1.83` and `strict` → every agent loses
> the API on restart → cluster-wide outage. Never use `--reuse-values`; always pass the values file below.

## Step 0 — make Helm match reality (stay on 1.14)

1. Write `cilium-values.yaml` (keep in git, e.g. the infra repo):

   ```yaml
   k8sServiceHost: 192.168.1.206
   k8sServicePort: 6443
   kubeProxyReplacement: false        # = live "partial" minus nothing: only socket LB was on
   socketLB:
     enabled: true                    # bpf-lb-sock=true today
   routingMode: tunnel
   tunnelProtocol: vxlan
   autoDirectNodeRoutes: false
   ipam: {mode: kubernetes}
   ipv4: {enabled: true}
   ipv6: {enabled: false}
   cni: {exclusive: true, install: true}
   l7Proxy: true
   loadBalancer: {mode: snat, acceleration: disabled}
   encryption: {enabled: false}
   policyEnforcementMode: default
   hubble: {enabled: true, relay: {enabled: true}, ui: {enabled: true, replicas: 1}}
   prometheus: {enabled: true}
   operator:
     replicas: 1
     resources: {limits: {cpu: 1000m, memory: 512Mi}, requests: {cpu: 100m, memory: 128Mi}}
   resources: {limits: {cpu: 1000m, memory: 1Gi}, requests: {cpu: 200m, memory: 256Mi}}
   ```

   `kubeProxyReplacement: false` + `socketLB.enabled` is accepted by 1.14 and is the 1.15+ spelling, so the same
   file carries through every step.
2. `helm diff upgrade cilium cilium/cilium -n kube-system --version 1.14.<latest> -f cilium-values.yaml`
   (helm-diff plugin) → expect only the image change, plus `kube-proxy-replacement: partial → false`, which is
   equivalent with just socket LB on. Anything else: stop and reconcile.
3. Upgrade to the **latest 1.14 patch** with that file (upstream: always go to the latest patch first).

## Each minor hop: 1.14 → 1.15 → 1.16 → 1.17 → 1.18 → 1.19 → 1.20

Per hop, nothing else changes in the same window:

1. Read that version's **Upgrade Notes** (docs.cilium.io/en/v1.N/operations/upgrade) and its **system
   requirements** (k8s version range). Fold required value renames into `cilium-values.yaml` (git commit per hop).
2. Preflight: `helm template cilium/cilium --version <target> -n kube-system --set preflight.enabled=true
   --set agent=false --set operator.enabled=false > preflight.yaml && kubectl create -f preflight.yaml`; wait for
   the `cilium-pre-flight-check` DaemonSet to be Ready on all 4 nodes (pre-pulls images, validates CNPs);
   `kubectl delete -f preflight.yaml`.
3. `helm diff upgrade ... --version <target> -f cilium-values.yaml` → review.
4. `helm upgrade cilium cilium/cilium -n kube-system --version <target> -f cilium-values.yaml`.
5. Verify (below). Soak ≥ 1 h, ideally a day for the first two hops.

Known per-hop items (verify against the notes; not exhaustive):

- **1.15:** `partial|strict|probe` KPR values gone (handled in step 0); `tunnel` Helm value gone (handled);
  in-pod CLI becomes `cilium-dbg`.
- **1.16:** Envoy moves to its own DaemonSet by default (`envoy.enabled`); `l7Proxy` traffic (L7 policies,
  Hubble L7) reconnects during the hop.
- **1.17–1.19:** check each "Removed Options" / "Helm options" list against the values file.
- **1.20:** removed flags list (e.g. `--k8s-api-server` → `k8s.apiServerURLs`); none of them are set here today.

## Verify after every step

- `kubectl -n kube-system rollout status ds/cilium` and `deploy/cilium-operator`.
- `kubectl -n kube-system exec ds/cilium -- cilium-dbg status` (or `cilium status` on 1.14): Kubernetes Ok,
  controllers healthy, **Cluster health 4/4**.
- No endpoint stuck enforced without a policy: `cilium-dbg endpoint list` on each agent; pods outside
  longhorn-system/styx/styx-instances/gitlab-redis must show `Disabled Disabled`.
- `kubectl get pods -A | grep -vE 'Running|Completed'` empty (minus known jobs).
- Ingress works: `curl -s -o /dev/null -w '%{http_code}' https://g.jmolabs.dev/` → 200; a Styx proxied
  service and a Longhorn volume attach (run the styx-db-backup job once).
- Optional: `cilium connectivity test` from a workstation with the cilium CLI (creates a test namespace).

## Safety

- **Before step 0:** `k3s etcd-snapshot save --name pre-cilium` on k1-n4; copy the Helm values and
  `helm get manifest cilium` output to the infra repo.
- **Rollback:** only to the previous minor: `helm rollback cilium <rev> -n kube-system` (the revision from that
  hop's `helm history`). Never jump back more than one minor.
- **Window:** each hop restarts every agent (a short per-node datapath blip; L7/proxy connections reset).
  Do it when nobody is in a Styx session; the cloudflared tunnel + Traefik run on k1-n4.
- k1-n4 is the **only** control-plane/etcd node: an API outage during a hop is what stranded pods last time.
  Do not combine with k3s upgrades or node reboots.

## Later (after 1.20)

- Decide on kube-proxy: keep (`kubeProxyReplacement: false`, as today) or go full replacement (`true`) and
  delete the kube-proxy DaemonSet — a separate change with its own window.
- Second control-plane node? Single etcd member = single point of failure (k1-n1 was once a server).
