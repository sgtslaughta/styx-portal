# Styx Enterprise — system design

Status: **Draft for owner approval** · 2026-10-28 · Source: owner grilling session (decisions D01–D59); revised after design review and owner decisions

## 1. Intent
One place where ~200–500 remote staff log in **with their CAC** and find their **containerized
desktops** and the **org's services** (wiki, chat, upstream GitLab) already there. Enterprise-grade:
fast, polished, highly secure, operable by a small team, and **authorizable (ATO)**. Guiding rule:
**low to no cost wherever possible** — open-source, self-hosted, no per-user license fees.

## 2. Goals / non-goals / anti-goals
**Goals:** smart-card-only access (CAC/PIV/PIV-I); ~150–200 concurrent desktops at peak; 99.9 % business-hours availability
for login/portal/services; golden desktop images patched automatically; data-loss controls for CUI;
every decision documented for the ATO; GPU tier addable later without re-architecture.

**Non-goals (v1):** multi-tenant isolation; session sharing/collaboration (v2); session recording;
live migration of running desktops; hosting GitLab locally; Nextcloud; physical-workstation
streaming for enterprise users.

**Anti-goals (failure even if it works):** anyone obtaining an account without an approved request;
passwords as a standing login method (break-glass excepted); CUI leaving through an unlogged channel;
a homelab outage affecting enterprise users; per-user license fees creeping in; a fork of Styx.

## 3. Context and constraints
- Data: **CUI**. Cards: **DoD CAC, federal PIV, PIV-I**. Users: single organization, no Active Directory.
- ATO under **RMF, NIST 800-53 Moderate + CUI overlay**, tracked in **eMASS**.
- FIPS-validated crypto and STIG baselines: **not required** (exceptions obtained); Ubuntu is fine.
- Hosting: **on-prem, new enterprise hardware**, one site. GPU funding later; **CPU-only first**.
- Ingress: **inbound 443 to a DMZ reverse proxy** (documented boundary, SC-7).
- Org assets: **M365 GCC High** (OneDrive, Forms, Power Automate), **federal GitLab** upstream,
  **Elastic** SIEM. No M365 service accounts.
- Ops: 2–3 people, business hours, best-effort after hours.

## 4. Architecture overview
```
 User (managed Windows/macOS, card reader)
   │ HTTPS 443 (client cert requested only on login.<domain>, D49)
   ▼
 DMZ HAProxy pair (D50)  ── allowlist: GCC High ranges → provision.<domain> only
   │
   ▼  RKE2 cluster (3 control plane + 8 GPU-ready workers), Cilium
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Traefik (in-cluster) → Styx portal (frontend, backend ×N on Postgres)     │
 │ Keycloak ×2 (X.509, EDIPI/UUID)  OpenBao (secrets, PKI)                   │
 │ Wiki.js · Matrix (Synapse+Element) · links to upstream GitLab             │
 │ Desktop pods (golden Ubuntu images, Selkies) ── egress via Squid  │
 │ Images pre-pulled · CephFS homes+profiles (Rook-Ceph) · CloudNativePG     │
 │ Harbor (images, Trivy, cosign) ← GitLab runners (upstream federal GitLab) │
 │ kube-prometheus-stack · Velero · Kyverno · External Secrets               │
 └──────────────────────────────────────────────────────────────────────────┘
   │ logs/audit → Elastic (90 d hot, 1 y archive)   age-off → Ceph RGW cold
   │ backups → CUI-authorized cloud bucket (encrypted)   user → OneDrive (GCC High) by hand
```

## 5. Decisions
Each row becomes an ADR in `adr/`. "Rationale" is the deciding reason; alternatives live in the ADR.

### Scope and platform
| ID | Decision | Rationale |
|---|---|---|
| D01 | Single organization; groups/departments, no multi-tenancy | Halves design; no resale plan |
| D02 | Keep Styx + Selkies as the product; no Kasm/Citrix | Selkies beats VNC; no license fees; workstation/services features |
| D03 | One codebase, two deployment profiles (homelab k3s / enterprise RKE2); never fork Styx. Enterprise profile hard-disables homelab-only features (D53) | One patch stream |
| D04 | Physical workstation seats stay homelab-only; enterprise users get container desktops | Remote users are all containerized |
| D05 | Low/no-cost open-source components preferred; any paid item needs an ADR. **Accepted costs:** Power Automate premium HTTP connector (D19), CUI offsite bucket (D37, ~$20–50/mo), Windows code-signing cert + Apple developer program (D41, ~$400/yr). Everything else free | Owner guiding rule; costs approved by owner |
| D06 | On-prem, new GPU-ready servers: 3 control plane, 8 workers (**each** 128 cores / 512 GB), 2 DMZ proxies | GPU funding = add cards, not servers |
| D07 | Kubernetes: RKE2, Cilium CNI | Enterprise-hardened, free; homelab stays k3s |
| D08 | Availability: 99.9 % business hours for login/portal/services; desktops may drop & reconnect on node loss. Planned maintenance (one announced evening window per month) is excluded from the 99.9 % | Containers can't live-migrate |
| D09 | Sizing: 150–200 concurrent (≈30–40 % of 500, office-hours pattern). Figures are per worker; N-1 budget: 7 surviving × 128 = 896 cores ≥ 200 desktops × 3 (600) + Ceph OSD reservations (~4 cores/node) + platform services (~100 cores) | Owner estimate; arithmetic holds with ~170 cores spare |

### Security baseline and ingress
| ID | Decision | Rationale |
|---|---|---|
| D10 | Compliance: RMF / 800-53 Moderate + CUI overlay; eMASS system of record; repo docs are source | ATO required |
| D11 | No FIPS/STIG engineering; exceptions recorded | Owner: exceptions obtained |
| D12 | Ingress: inbound 443 to a DMZ reverse-proxy pair (HAProxy, D50); no Cloudflare/overlay | CAC mTLS ends on-prem; shortest stream path; compliant boundary |
| D13 | All decisions documented as ADRs + control matrix in repo | ATO evidence |
| D48 | Code provenance: federal GitLab is the source of truth for the enterprise build; GitHub becomes a mirror; merges that ship into the ATO boundary are approved there | New decision; builds and approvals inside the boundary |
| D49 | Hostnames: banner host (no client-cert request; shows AC-8 banner first) → `login.<domain>` (CAC mTLS, Keycloak); `provision.<domain>` (mTLS with OpenBao CA, webhook only, GCC High IP allowlist); portal/stream host (no client-cert request). Desktops path-routed (`/i/<sub>`), so no wildcard cert; server certs from org/DoD-issued CA or free ACME as allowed | Builder call |
| D50 | DMZ proxy = HAProxy pair terminating TLS and forwarding the client cert in a header format Keycloak's x509 lookup SPI supports; in-cluster Traefik behind it | Builder call |

### Identity
| ID | Decision | Rationale |
|---|---|---|
| D14 | Keycloak is the identity provider and the user directory (no AD), authoritative for users and groups (D51) | Mature X.509/CAC, free |
| D15 | Authentication: **smart card only** — DoD CAC, federal PIV and PIV-I all accepted. Trust anchors: DoD roots + Federal Common Policy CA (+ FBCA cross-certified PIV-I issuers). Only the PIV Authentication certificate is accepted (not signing/encryption). No card → no access. No FIDO2/TOTP/password fallback | Phishing-resistant; simplest policy; staff hold mixed card types |
| D16 | Card ↔ account key: **EDIPI for CAC; card UUID (PIV Authentication cert SAN `urn:uuid`) for PIV/PIV-I**, hidden attributes. Bound at first login: an approved request (name, email, card type, EDIPI if CAC) is matched by the first card login whose cert name/email matches it, which binds the card id; mismatch → held for admin review. Card reissue → help-desk rebind (logged). Visible username `first.last` (+digit on collision), display "Last, First M."; username immutable | Readable audit, stable identity; PIV-I has no EDIPI |
| D17 | Revocation: OCSP primary (per issuer) + local CRL mirror (cronjob) read by path in Keycloak; alert on CRL age | DoD/federal PKI practice; builder call: mirror avoids per-login CRL fetches |
| D18 | **No self-enrollment.** Accounts exist only from an approved request (webhook) or admin CSV import; a CAC alone never creates an account | Owner anti-goal |
| D19 | Provisioning: M365 Form → Power Automate approval → HTTPS webhook (SCIM-shaped) into Styx → Keycloak. Premium HTTP connector licensed (D05); the flow has two licensed named co-owners; cost recorded | Org tooling; no M365 service account |
| D20 | Webhook hardening: mTLS (OpenBao-issued client cert, yearly) + bearer token (90-day) + GCC High IP allowlist at DMZ + approval-ID check + approver validation + strict schema + idempotent + non-admin groups only + every call audited. Approver validation means Styx checks the asserted approver is a known group manager; it **cannot verify the M365 approval itself** — the real control is the D23 human review (R04) | Only door into the system |
| D21 | Form fields: first, last, email, card type (CAC/PIV/PIV-I), EDIPI (CAC only), groups, approving manager, end date (required for contractors) | Request links form to card (D16); end date auto-offboards |
| D22 | Offboarding: "Remove access" flow → disable (sessions killed now); end date auto-disable; 35-day inactivity disable; delete after 90-day review counted from the disable date | Three independent off-switches (AC-2, PS-4) |
| D23 | New accounts surface in admin "Recently provisioned" + daily digest (portal + Matrix) to security officer; one-click suspend | Human sees every new account within a day |
| D24 | Quarterly access review: admin-console report per group manager with certify/revoke actions + CSV export; admin CSV import must reference an approval record | AC-2(3); builder call on format |
| D25 | Break-glass: two local Keycloak admins (username + password + TOTP), alerting ops + security officer on use. Break-glass set is escrowed in OpenBao **and** offline (sealed, in the safe): offline RKE2 kubeconfig, OpenBao root/recovery, Ceph admin key, Styx emergency admin (see D42) | Only password accounts; OpenBao must not be the only copy |
| D26 | Admin roles: platform admin, help desk, auditor (read-only), group manager; admin roles granted only in Keycloak by platform admins | AC-5 separation of duties |
| D27 | USG system-use banner shown on a banner host that does not request a client cert, before the user is sent to the CAC login host (D49) | AC-8 |
| D51 | Keycloak is authoritative for users/groups; Styx mirrors groups from OIDC claims. Styx's Keycloak admin client is limited by fine-grained admin permissions to create/update/disable ordinary users and non-admin group membership (no role mapping) | Builder call; limits blast radius of a Styx compromise |
| D52 | Styx allocates an immutable POSIX UID per user (stored as a Keycloak attribute) for CephFS homes | Builder call |
| D53 | Enterprise profile hard-disables password login, matrix-card 2FA, generic OIDC providers, workstation enrollment and Docker routers; verified by a config test + a diagnostics endpoint listing enabled features | Builder call; least functionality (CM-7) |

### Desktops and data
| ID | Decision | Rationale |
|---|---|---|
| D28 | Golden images: 3–5 Ubuntu-based images (base-office, developer, browser-only, GPU later) built in CI on upstream federal GitLab with on-prem runners | Owned, patched, small set |
| D29 | Supply chain: nightly rebuild, Trivy scan, cosign sign + SBOM, Harbor registry, Kyverno admits only signed allowlisted images | Automatic secure updates |
| D30 | Image rollout: new image applies at next launch/restart, never mid-session; critical CVE → running sessions warned and recycled within 24 h (the former ">7 days recycle" is dropped as moot with the 12 h max) | Never mid-session |
| D31 | CPU tier capped 1080p / 30 fps / HiDPI off; ~3 cores + 4 GB per concurrent desktop; per-group override | CPU-only until GPU funding |
| D32 | GPU tier later: SR-IOV-capable cards (Intel Flex class), no vGPU license | No per-user fees |
| D33 | Storage: Rook-Ceph on worker NVMe (CephFS homes and profiles, RBD volumes, RGW S3 incl. cold archive) | Free, one system |
| D34 | Home: 10 GB quota/user (warn 80 %), mounted in every desktop; per-app persistent profiles 2 GB, as CephFS subvolumes (D54) | Conservative storage |
| D35 | Age-off: home files untouched 90 d → 14-day notice → automatic move to on-prem Ceph RGW cold storage (object lock, lifecycle) with user self-restore from the portal; users may move files to OneDrive (GCC High) themselves from the browser inside their desktop (allowed by egress); no automatic OneDrive transfer (no service account, no live token). Profiles unused 60 d deleted after notice; with daily stop, per-instance scratch volumes reclaimed after 7 d stopped (persistent data belongs in home/profile); user "Send to archive" anytime | Limited storage; no M365 service account |
| D36 | Styx database: SQLite → PostgreSQL (CloudNativePG, 3 instances); backend multi-replica; migration details in D56 | Scale + HA |
| D37 | Backup/DR: RPO 24 h / RTO 8 h; CNPG + Velero + nightly home snapshots; offsite = encrypted copy to a CUI-authorized cloud bucket (~$20–50/mo, accepted) using CephFS snapshot-based incremental export; full-site restore test in phase 1. No alternate processing site: CP-7 is an exception (R03) | Moderate-impact norm |
| D54 | Profiles move from RBD to CephFS subvolumes (RWX, reattach after node loss); non-graceful node-shutdown handling automated | Builder call; faster recovery |
| D55 | Ceph: per-node CPU/memory reservation for OSDs; recovery throttled in business hours | Builder call; Ceph co-located with desktops |
| D56 | Styx Postgres migration: Alembic; leader election (Postgres advisory lock) for background loops; lockout/rate-limit state in Postgres; DB credentials are CNPG-managed roles with periodic rotation + rolling restart | Builder call |
| D57 | Desktop base image: own rootless Selkies + pixelflux Ubuntu base (not linuxserver.io); the desktop namespace carries a documented Pod Security Admission exception | Builder call |
| D58 | Selkies: a maintained patch set (upstream where possible) for audit events, lock-overlay hook and encoder-burned watermark. "Never fork" (D03) applies to Styx | Builder call |

### Session security
| ID | Decision | Rationale |
|---|---|---|
| D38 | DLP defaults (per-group override): clipboard text both ways; file upload in allowed, download out off; local printing off; watermark user+time on. Clipboard/file events are logged as **metadata only** (user, time, direction, size, type, filename hash) — never content; Elastic is not a CUI store | CUI handling |
| D39 | Session timeouts: 15 min idle → lock; 2 h disconnected → stop; 12 h max. The lock lives in the Styx gateway (stops forwarding the stream + overlay); unlock = a fresh TLS handshake with session resumption disabled, which proves card presence, **not PIN entry** (R02) | AC-11, AC-12; builder call on mechanism |
| D40 | Egress: internet **allowed by default with content/category blocking** — Squid + free category blocklists (e.g. UT1) with e2guardian-style filtering; file-sharing, webmail, paste sites and anonymizers blocked; **no SSL-bump** (no TLS decryption), so filtering is by hostname/SNI and hostnames are logged to Elastic. LAN only to approved services. Cilium denies all non-proxy egress (incl. SSH, UDP/WebRTC). Allowlist mode per group remains. SC-7(5) is tailored (R01) | SC-7, AU; owner decision |
| D41 | Smart-card passthrough (**phase 4**): own open-source helper (vpcd/virtualsmartcard-based), signed (Windows code-signing cert, Apple developer program), MDM-pushed, Windows first then macOS; relays PC/SC only to the user's own session; authenticates with its own CAC mTLS + a per-session one-time token; APDU allowlist; signing only with user interaction; own threat model | Pilots need the card inside the desktop; browsers can't reach readers; no license |
| D42 | Secrets: OpenBao (MPL fork of Vault) for app secrets via External Secrets, internal PKI, backup keys, break-glass escrow. **Auto-unseal** (TPM/key-file on control plane; no human unseal on restart); Shamir recovery keys held by 3 people for disaster only. Break-glass credentials and backup encryption keys are also escrowed offline (sealed, in the safe). DB credentials are CNPG-managed roles (D56), not Vault dynamic leases | No BSL ambiguity; restarts need no humans |

### Services, operations, experience
| ID | Decision | Rationale |
|---|---|---|
| D43 | Services: upstream federal GitLab (link only, not under our SSO claim), Wiki.js, Matrix (Synapse + Element), OIDC to Keycloak; non-OIDC apps behind Styx forwardAuth; Nextcloud dropped (OneDrive covers files) | Free with SSO |
| D44 | Observability: kube-prometheus-stack + Elastic (90 d hot / 1 y archive); SLO dashboards (login, launch time, stream latency, headroom); stream-latency SLO measured by a client-side RTT metric reported to Prometheus; alerts and notifications via portal + Matrix (SMTP relay optional if the org provides one later, D59) | Free |
| D59 | Notifications via portal + Matrix; org SMTP relay is unknown, so SMTP is an optional config if one is provided later | Owner decision |
| D45 | Help-desk **shadowing** (support, consent) is distinct from **sharing** (peer collaboration, v2): user consent to view, second consent to control, "being viewed" banner, logged; two-stage consent implemented in the Styx gateway | Supportability; builder call |
| D46 | Enterprise UX: home = My desktops / My services / announcements; desktops open in own tab with slim toolbar; launch target 8–10 s (users can wait): images pre-pulled on all workers, home/profile mounted at pod start; per-image warm pools dropped from v1 (optional later: per-user scheduled pre-warm); design system light/dark + org branding; self-service (quota, files, profiles, sessions); status/maintenance banner + in-app notifications; separate role-gated admin console (live sessions, capacity, user detail, policy editor); Section 508 / WCAG 2.1 AA | "Citrix Workspace / AVD feel" bar |
| D47 | Rollout: pilot 25 (after phase 4) → 100 (after phase 5) → all users after the load-test gate, which follows phase 5 and does **not** wait for phase 6 (200-session synthetic soak, launch p95 < 10 s, stream p95 < 80 ms measured client-side, 0 drops over 4 h) | Evidence before scale |

## 6. Roadmap
| Phase | Delivers | Exit |
|---|---|---|
| 1 Foundation | RKE2, Rook-Ceph (OSD reservations), CNPG, Harbor, OpenBao (auto-unseal), DMZ HAProxy pair, monitoring + Elastic shipping; Styx on Postgres, multi-replica; offsite export | Styx HA demo, full-site restore tested |
| 2 Identity | Keycloak CAC/PIV/PIV-I, webhook provisioning (D19–D23), card binding, offboarding, roles, banner, break-glass | Form → account → card login → offboard, all audited |
| 3 Desktops | Own base image + golden images + supply chain, homes/quotas/profiles on CephFS, CPU caps, Squid category-filtered egress | Signed image launch, home follows user |
| 4 Session security | DLP, watermark, gateway lock, timeouts, metadata event logging, smart-card helper (Win → mac) | **Pilot 25** |
| 5 Enterprise UX | Pre-pulled fast launch, shadowing, age-off to Ceph RGW, Wiki.js + Matrix, admin console, 508 pass | **Pilot 100**, load-test gate → **All users** |
| 6 GPU | GPU tier on funding | Does not gate "all users" |

## 7. Open items for the builder
Exact Keycloak X.509 flow config (HAProxy cert-header format vs the x509 lookup SPI) and the SCIM subset
— each resolved in its own ADR during its phase.

## 8. Risk acceptances and tailoring
Each item needs an owner signature in eMASS (POA&M or tailoring record).

| ID | Control | Item | Compensating controls |
|---|---|---|---|
| R01 | SC-7(5) | Deny-by-default is tailored: internet egress is allowed by default with category blocking (D40). Residual exfiltration risk via uncategorized sites accepted | Category blocking, DLP download-off (D38), hostname logging to Elastic, watermark, Cilium denies all non-proxy egress |
| R02 | AC-11 | Lock lives in the Styx gateway; unlock is a fresh TLS handshake (resumption disabled), which proves card presence, not PIN entry (D39) | 15 min idle lock, 12 h max, card required in reader, audit of unlocks |
| R03 | CP-7 | No alternate processing site (single site, D06/D37) — exception | Encrypted offsite backups (CP-6), RTO 8 h restore tested in phase 1 |
| R04 | IA-12 / AC-2 | Styx cannot verify the M365 approval; it only checks the asserted approver is a known group manager (D20) | mTLS + token + IP allowlist, D23 human review of every new account within a day, one-click suspend |
| R05 | SC-13 / CM-6 | No FIPS-validated crypto or STIG baseline (D11) | Exceptions already obtained; recorded in eMASS |
| R06 | IA-2 | Break-glass password+TOTP accounts are an exception to smart-card-only (D25) | Two accounts only, offline escrow, alert on every use, annual test |
