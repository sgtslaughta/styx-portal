# Styx Enterprise — system design

Status: **Draft for owner approval** · 2026-10-28 · Source: owner grilling session (decisions D01–D47)

## 1. Intent
One place where ~200–500 remote staff log in **with their CAC** and find their **containerized
desktops** and the **org's services** (wiki, chat, upstream GitLab) already there. Enterprise-grade:
fast, polished, highly secure, operable by a small team, and **authorizable (ATO)**. Guiding rule:
**low to no cost wherever possible** — open-source, self-hosted, no per-user license fees.

## 2. Goals / non-goals / anti-goals
**Goals:** CAC-only access; ~150–200 concurrent desktops at peak; 99.9 % business-hours availability
for login/portal/services; golden desktop images patched automatically; data-loss controls for CUI;
every decision documented for the ATO; GPU tier addable later without re-architecture.

**Non-goals (v1):** multi-tenant isolation; session sharing/collaboration (v2); session recording;
live migration of running desktops; hosting GitLab locally; Nextcloud; physical-workstation
streaming for enterprise users.

**Anti-goals (failure even if it works):** anyone obtaining an account without an approved request;
passwords as a standing login method (break-glass excepted); CUI leaving through an unlogged channel;
a homelab outage affecting enterprise users; per-user license fees creeping in; a fork of Styx.

## 3. Context and constraints
- Data: **CUI**. Cards: **DoD PIV/CAC**. Users: single organization, no Active Directory.
- ATO under **RMF, NIST 800-53 Moderate + CUI overlay**, tracked in **eMASS**.
- FIPS-validated crypto and STIG baselines: **not required** (exceptions obtained); Ubuntu is fine.
- Hosting: **on-prem, new enterprise hardware**, one site. GPU funding later; **CPU-only first**.
- Ingress: **inbound 443 to a DMZ reverse proxy** (documented boundary, SC-7).
- Org assets: **M365 GCC High** (OneDrive, Forms, Power Automate), **federal GitLab** upstream,
  **Elastic** SIEM. No M365 service accounts.
- Ops: 2–3 people, business hours, best-effort after hours.

## 4. Architecture overview
```
 User (managed Windows/macOS, CAC reader)
   │ HTTPS 443 (mTLS optional at TLS, required by Keycloak for login)
   ▼
 DMZ reverse proxy pair (HAProxy/Traefik)  ── allowlist: GCC High ranges → /provisioning only
   │
   ▼  RKE2 cluster (3 control plane + ~8 GPU-ready workers), Cilium
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Traefik (in-cluster) → Styx portal (frontend, backend ×N on Postgres)     │
 │ Keycloak ×2 (X.509/CAC, EDIPI match)   OpenBao (secrets, PKI)              │
 │ Wiki.js · Matrix (Synapse+Element) · links to upstream GitLab             │
 │ Desktop pods (golden Ubuntu images, Selkies) ── egress only via Squid     │
 │ Warm pools · CephFS homes + RBD profiles (Rook-Ceph) · CloudNativePG      │
 │ Harbor (images, Trivy, cosign) ← GitLab runners (upstream federal GitLab) │
 │ kube-prometheus-stack · Velero · Kyverno · External Secrets               │
 └──────────────────────────────────────────────────────────────────────────┘
   │ logs/audit → Elastic (90 d hot, 1 y archive)   archive → OneDrive (GCC High)
   │ backups → CUI-authorized cloud bucket (encrypted)
```

## 5. Decisions
Each row becomes an ADR in `adr/`. "Rationale" is the deciding reason; alternatives live in the ADR.

### Scope and platform
| ID | Decision | Rationale |
|---|---|---|
| D01 | Single organization; groups/departments, no multi-tenancy | Halves design; no resale plan |
| D02 | Keep Styx + Selkies as the product; no Kasm/Citrix | Selkies beats VNC; no license fees; workstation/services features |
| D03 | One codebase, two deployment profiles (homelab k3s / enterprise RKE2); never fork | One patch stream |
| D04 | Physical workstation seats stay homelab-only; enterprise users get container desktops | Remote users are all containerized |
| D05 | Low/no-cost open-source components preferred; any paid item needs an ADR | Owner guiding rule |
| D06 | On-prem, new GPU-ready servers: 3 control plane, ~8 workers (96–128 cores, 512 GB), 2 DMZ proxies | GPU funding = add cards, not servers |
| D07 | Kubernetes: RKE2, Cilium CNI | Enterprise-hardened, free; homelab stays k3s |
| D08 | Availability: 99.9 % business hours for login/portal/services; desktops may drop & reconnect on node loss | Containers can't live-migrate |
| D09 | Sizing: 150–200 concurrent (≈30–40 % of 500, office-hours pattern) | Owner estimate |

### Security baseline and ingress
| ID | Decision | Rationale |
|---|---|---|
| D10 | Compliance: RMF / 800-53 Moderate + CUI overlay; eMASS system of record; repo docs are source | ATO required |
| D11 | No FIPS/STIG engineering; exceptions recorded | Owner: exceptions obtained |
| D12 | Ingress: inbound 443 to DMZ reverse-proxy pair; no Cloudflare/overlay | CAC mTLS ends on-prem; shortest stream path; compliant boundary |
| D13 | All decisions documented as ADRs + control matrix in repo | ATO evidence |

### Identity
| ID | Decision | Rationale |
|---|---|---|
| D14 | Keycloak is the identity provider and the user directory (no AD) | Mature X.509/CAC, free |
| D15 | Authentication: **CAC only**. No CAC → no access. No FIDO2/TOTP/password fallback | Phishing-resistant; simplest policy |
| D16 | Card ↔ account key: EDIPI (hidden attribute). Visible username `first.last` (+digit on collision), display "Last, First M."; username immutable | Readable audit, stable identity |
| D17 | Revocation: OCSP on every login, cached CRL fallback | DoD PKI practice |
| D18 | **No self-enrollment.** Accounts exist only from an approved request (webhook) or admin CSV import; a CAC alone never creates an account | Owner anti-goal |
| D19 | Provisioning: M365 Form → Power Automate approval → HTTPS webhook (SCIM-shaped) into Styx → Keycloak | Org tooling; no M365 service account |
| D20 | Webhook hardening: mTLS (OpenBao-issued client cert, yearly) + bearer token (90-day) + GCC High IP allowlist at DMZ + approval-ID/approver validation + strict schema + idempotent + non-admin groups only + every call audited | Only door into the system |
| D21 | Form fields: first, last, EDIPI, email, groups, approving manager, end date (required for contractors) | EDIPI links form to card; end date auto-offboards |
| D22 | Offboarding: "Remove access" flow → disable (sessions killed now); end date auto-disable; 35-day inactivity disable; delete after 90-day review | Three independent off-switches (AC-2, PS-4) |
| D23 | New accounts surface in admin "Recently provisioned" + daily digest to security officer; one-click suspend | Human sees every new account within a day |
| D24 | Quarterly access-review report per group manager | AC-2(3) |
| D25 | Break-glass: two local Keycloak admins (username + password + TOTP), creds escrowed in OpenBao, use alerts ops + security officer | Only password accounts |
| D26 | Admin roles: platform admin, help desk, auditor (read-only), group manager; admin roles granted only in Keycloak by platform admins | AC-5 separation of duties |
| D27 | USG system-use banner before login | AC-8 |

### Desktops and data
| ID | Decision | Rationale |
|---|---|---|
| D28 | Golden images: 3–5 Ubuntu-based images (base-office, developer, browser-only, GPU later) built in CI on upstream federal GitLab with on-prem runners | Owned, patched, small set |
| D29 | Supply chain: nightly rebuild, Trivy scan, cosign sign + SBOM, Harbor registry, Kyverno admits only signed allowlisted images | Automatic secure updates |
| D30 | Image rollout: new image at next launch/restart; sessions >7 days recycled after warning; critical CVE → 24 h | Never mid-session |
| D31 | CPU tier capped 1080p / 30 fps / HiDPI off; ~3 cores + 4 GB per concurrent desktop; per-group override | CPU-only until GPU funding |
| D32 | GPU tier later: SR-IOV-capable cards (Intel Flex class), no vGPU license | No per-user fees |
| D33 | Storage: Rook-Ceph on worker NVMe (CephFS homes, RBD volumes, RGW S3) | Free, one system |
| D34 | Home: 10 GB quota/user (warn 80 %), mounted in every desktop; per-app persistent profiles 2 GB | Conservative storage |
| D35 | Age-off: home files untouched 90 d → 14-day notice → OneDrive (GCC High) archive; profiles unused 60 d deleted after notice; stopped-instance volumes reclaimed after 7 d; user "Send to archive" anytime | Limited storage |
| D36 | Styx database: SQLite → PostgreSQL (CloudNativePG, 3 instances); backend multi-replica | Scale + HA |
| D37 | Backup/DR: RPO 24 h / RTO 8 h; CNPG + Velero + nightly home snapshots; encrypted offsite copy to CUI-authorized cloud bucket (no second site) | Moderate-impact norm |

### Session security
| ID | Decision | Rationale |
|---|---|---|
| D38 | DLP defaults (per-group override): clipboard text both ways; file upload in allowed, download out off; local printing off; watermark user+time on; all transfers/clipboard events logged | CUI handling |
| D39 | Session timeouts: 15 min idle → stream lock, re-auth with CAC PIN; 2 h disconnected → stop; 12 h max | AC-11, AC-12 |
| D40 | Desktop egress only via on-prem Squid forward proxy (URLs logged to Elastic); internet default-allow minus blocklist; LAN only to approved services; allowlist mode per group | SC-7, AU |
| D41 | Smart-card passthrough: own open-source helper (vpcd/virtualsmartcard-based), signed, MDM-pushed, Windows first then macOS; relays PC/SC only to the user's own session over the authenticated connection; own threat model | Browsers can't reach card readers; no license |
| D42 | Secrets: OpenBao (MPL fork of Vault) for dynamic DB creds, app secrets via External Secrets, internal PKI, backup keys, break-glass escrow; Shamir unseal split across 3 people | No BSL ambiguity |

### Services, operations, experience
| ID | Decision | Rationale |
|---|---|---|
| D43 | Services: upstream federal GitLab (linked), Wiki.js, Matrix (Synapse + Element), all OIDC to Keycloak; non-OIDC apps behind Styx forwardAuth; Nextcloud dropped (OneDrive covers files) | Free with SSO |
| D44 | Observability: kube-prometheus-stack + Elastic (90 d hot / 1 y archive); SLO dashboards (login, launch time, stream latency, headroom); alerts to ops email/Matrix | Free |
| D45 | Help-desk shadowing: user consent to view, second consent to control, "being viewed" banner, logged | Supportability |
| D46 | Enterprise UX: home = My desktops / My services / announcements; desktops open in own tab with slim toolbar; warm pools (~10 % of peak, time-of-day) for ~3 s launch; design system light/dark + org branding; self-service (quota, files, profiles, sessions); status/maintenance banner + in-app notifications; separate role-gated admin console (live sessions, capacity, user detail, policy editor); Section 508 / WCAG 2.1 AA | "Citrix Workspace / AVD feel" bar |
| D47 | Rollout: pilot 25 (after phase 4) → 100 (after phase 5) → all after load-test gate (250-session synthetic soak, launch p95 < 10 s, stream p95 < 80 ms, 0 drops over 4 h) | Evidence before scale |

## 6. Roadmap
| Phase | Delivers | Exit |
|---|---|---|
| 1 Foundation | RKE2, Rook-Ceph, CNPG, Harbor, OpenBao, DMZ proxies, monitoring + Elastic shipping; Styx on Postgres, multi-replica | Styx HA demo, backups restore-tested |
| 2 Identity | Keycloak CAC/EDIPI, webhook provisioning (D19–D23), offboarding, roles, banner, break-glass | Form → account → CAC login → offboard, all audited |
| 3 Desktops | Golden images + supply chain, homes/quotas/profiles, CPU caps, Squid egress | Signed image launch, home follows user |
| 4 Session security | DLP, watermark, lock/stop/max timeouts, event logging | **Pilot 25** |
| 5 Enterprise UX | Warm pools, shadowing, age-off/archive, Wiki.js + Matrix, admin console, 508 pass | **Pilot 100**, load-test gate |
| 6 Passthrough + GPU | Card helper (Win → mac), GPU tier on funding | **All users** |

## 7. Open items for the builder
Exact Keycloak X.509 flow config; SCIM subset; Squid blocklist source; warm-pool sizing algorithm;
lock-screen mechanism inside Selkies; OneDrive transfer mechanism without an M365 service account
(likely user-delegated OAuth at archive time) — each resolved in its own ADR during its phase.
