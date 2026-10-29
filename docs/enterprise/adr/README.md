# Architecture Decision Records

All ADRs are Proposed pending owner approval of design.md. One ADR per decision D01-D59.

| ID | Title | Status | Controls |
|---|---|---|---|
| [D01](0001-single-organization-groups-instead-of-multi-tenancy.md) | Single organization, groups instead of multi-tenancy | Proposed | AC-2, AC-3, AC-6 |
| [D02](0002-keep-styx-and-selkies-as-the-product-no-kasm-or-citrix.md) | Keep Styx and Selkies as the product; no Kasm or Citrix | Proposed | SA-4, SA-9, SC-7 |
| [D03](0003-one-codebase-two-deployment-profiles-never-fork.md) | One codebase, two deployment profiles; never fork | Proposed | CM-2, CM-3, SA-10, SI-2 |
| [D04](0004-physical-workstation-seats-stay-homelab-only.md) | Physical workstation seats stay homelab-only | Proposed | AC-17, CM-7 |
| [D05](0005-prefer-low-no-cost-open-source-components-paid-items-require.md) | Prefer low/no-cost open-source components; paid items require an ADR | Proposed | SA-4, SA-9, SR-3 |
| [D06](0006-on-prem-gpu-ready-hardware-3-control-plane-8-workers-2-dmz-p.md) | On-prem GPU-ready hardware: 3 control plane, 8 workers, 2 DMZ proxies | Proposed | CP-2, PE-3, SC-7, SA-4 |
| [D07](0007-kubernetes-distribution-rke2-with-cilium-cni.md) | Kubernetes distribution: RKE2 with Cilium CNI | Proposed | CM-6, CM-7, SC-7, AC-4, SI-2 |
| [D08](0008-availability-99-9-business-hours-for-login-portal-services.md) | Availability: 99.9% business hours for login/portal/services | Proposed | CP-2, CP-10, SI-13 |
| [D09](0009-sizing-150-200-concurrent-desktops-at-peak.md) | Sizing: 150-200 concurrent desktops at peak | Proposed | CP-2, SC-5 |
| [D10](0010-compliance-rmf-800-53-moderate-plus-cui-overlay-emass-as-sys.md) | Compliance: RMF, 800-53 Moderate plus CUI overlay, eMASS as system of record | Proposed | CA-1, CA-2, CA-6, PL-2, RA-3 |
| [D11](0011-no-fips-or-stig-engineering-exceptions-recorded.md) | No FIPS or STIG engineering; exceptions recorded | Proposed | CM-6, SC-13, SA-4 |
| [D12](0012-ingress-inbound-443-to-a-dmz-reverse-proxy-pair-no-cloudflar.md) | Ingress: inbound 443 to a DMZ reverse-proxy pair; no Cloudflare or overlay | Proposed | SC-7, SC-8, SC-23, AC-17 |
| [D13](0013-document-every-decision-as-an-adr-plus-control-matrix-in-rep.md) | Document every decision as an ADR plus control matrix in repo | Proposed | CA-2, PL-2, SA-5 |
| [D14](0014-keycloak-as-identity-provider-and-user-directory-no-active-d.md) | Keycloak as identity provider and user directory; no Active Directory | Proposed | IA-2, IA-4, IA-5, AC-2 |
| [D15](0015-smart-card-only-authentication-cac-piv-piv-i-no-fallback.md) | Smart-card-only authentication (CAC, PIV, PIV-I); no fallback factors | Proposed | IA-2, IA-2(12), IA-5(2), IA-8 |
| [D16](0016-card-to-account-key-edipi-or-piv-uuid-username-first-last-immutable.md) | Card-to-account key is EDIPI (CAC) or card UUID (PIV/PIV-I); username first.last, immutable | Proposed | IA-4, IA-5, AU-3 |
| [D17](0017-revocation-ocsp-on-every-login-cached-crl-fallback.md) | Revocation: OCSP on every login, cached CRL fallback | Proposed | IA-5(2), SC-17, IA-2(12) |
| [D18](0018-no-self-enrollment-accounts-only-from-approved-requests.md) | No self-enrollment; accounts only from approved requests | Proposed | AC-2, IA-4, IA-12 |
| [D19](0019-provisioning-via-m365-form-power-automate-approval-https-web.md) | Provisioning via M365 Form, Power Automate approval, HTTPS webhook | Proposed | AC-2, AC-2(1), IA-4 |
| [D20](0020-webhook-hardening.md) | Webhook hardening | Proposed | AC-3, AC-17, IA-3, IA-5, SC-7, SC-8, SI-10, AU-2 |
| [D21](0021-request-form-fields.md) | Request form fields | Proposed | AC-2, IA-4, PS-4 |
| [D22](0022-offboarding-three-independent-off-switches.md) | Offboarding: three independent off-switches | Proposed | AC-2, AC-2(3), PS-4, PS-5 |
| [D23](0023-visibility-of-new-accounts-recently-provisioned-view-and-dai.md) | Visibility of new accounts: Recently provisioned view and daily digest | Proposed | AC-2(4), AU-6, AU-12 |
| [D24](0024-quarterly-access-review-report-per-group-manager.md) | Quarterly access-review report per group manager | Proposed | AC-2, AC-2(3), AC-6 |
| [D25](0025-break-glass-two-local-keycloak-admins-with-password-and-totp.md) | Break-glass: two local Keycloak admins with password and TOTP | Proposed | AC-2, IA-2, IA-5, AU-6, AC-2(2) |
| [D26](0026-admin-roles-platform-admin-help-desk-auditor-group-manager.md) | Admin roles: platform admin, help desk, auditor, group manager | Proposed | AC-2, AC-5, AC-6, AU-9 |
| [D27](0027-usg-system-use-banner-before-login.md) | USG system-use banner before login | Proposed | AC-8 |
| [D28](0028-golden-images-3-5-ubuntu-based-images-built-in-ci.md) | Golden images: 3-5 Ubuntu-based images built in CI | Proposed | CM-2, CM-3, CM-6, SA-10 |
| [D29](0029-supply-chain-nightly-rebuild-scan-sign-sbom-harbor-kyverno-a.md) | Supply chain: nightly rebuild, scan, sign, SBOM, Harbor, Kyverno admission | Proposed | SR-3, SR-4, SI-2, SI-7, RA-5, CM-7 |
| [D30](0030-image-rollout-next-launch-24-hour-critical-cve-recycle.md) | Image rollout: next launch, 24-hour critical-CVE recycle | Proposed | SI-2, CM-3, RA-5 |
| [D31](0031-cpu-tier-caps-1080p-30-fps-hidpi-off-3-cores-and-4-gb-per-de.md) | CPU tier caps: 1080p, 30 fps, HiDPI off; ~3 cores and 4 GB per desktop | Proposed | SC-5, SC-6, CM-6 |
| [D32](0032-gpu-tier-later-sr-iov-capable-cards-no-vgpu-license.md) | GPU tier later: SR-IOV-capable cards, no vGPU license | Proposed | SA-4, SC-6 |
| [D33](0033-storage-rook-ceph-on-worker-nvme.md) | Storage: Rook-Ceph on worker NVMe | Proposed | CP-9, SC-28, SC-5 |
| [D34](0034-home-quota-10-gb-per-user-2-gb-per-app-profiles.md) | Home quota 10 GB per user; 2 GB per-app profiles | Proposed | SC-5, SC-28, CM-12 |
| [D35](0035-age-off-to-ceph-rgw-cold-storage-with-self-restore.md) | Age-off to Ceph RGW cold storage with user self-restore | Proposed | MP-6, SI-12, CM-12, SC-28 |
| [D36](0036-styx-database-sqlite-to-postgresql-via-cloudnativepg.md) | Styx database: SQLite to PostgreSQL via CloudNativePG | Proposed | CP-9, CP-10, SC-28, SC-5 |
| [D37](0037-backup-and-dr-rpo-24-h-rto-8-h-encrypted-offsite-copy.md) | Backup and DR: RPO 24 h, RTO 8 h; encrypted offsite copy | Proposed | CP-9, CP-10, CP-6, CP-7, SC-28 |
| [D38](0038-dlp-defaults-with-per-group-override.md) | DLP defaults with per-group override | Proposed | AC-4, SC-7, AU-2, AU-12, MP-7 |
| [D39](0039-session-timeouts-15-min-idle-lock-2-h-disconnect-stop-12-h-m.md) | Session timeouts: 15 min idle lock, 2 h disconnect stop, 12 h max | Proposed | AC-11, AC-12, SC-10 |
| [D40](0040-desktop-egress-only-via-on-prem-squid-proxy.md) | Desktop egress via on-prem Squid with category blocking | Proposed | SC-7, SC-7(5), AU-2, AU-12, AC-4 |
| [D41](0041-smart-card-passthrough-via-own-open-source-helper.md) | Smart-card passthrough via own open-source helper (phase 4) | Proposed | IA-2(12), SA-8, SA-11, SC-12 |
| [D42](0042-secrets-openbao-with-external-secrets.md) | Secrets: OpenBao with External Secrets, auto-unseal and offline escrow | Proposed | SC-12, SC-13, SC-28, IA-5, SC-17 |
| [D43](0043-services-upstream-gitlab-link-wiki-js-matrix-oidc-to-keycloa.md) | Services: upstream GitLab link, Wiki.js, Matrix; OIDC to Keycloak | Proposed | IA-2, AC-3, SC-23 |
| [D44](0044-observability-kube-prometheus-stack-and-elastic.md) | Observability: kube-prometheus-stack and Elastic | Proposed | AU-2, AU-3, AU-6, AU-11, SI-4, IR-4 |
| [D45](0045-help-desk-shadowing-with-consent.md) | Help-desk shadowing with consent | Proposed | AC-2, AC-6, AU-2, AC-17 |
| [D46](0046-enterprise-ux-standard.md) | Enterprise UX standard | Proposed | AT-2, SA-8, AU-2, AC-6 |
| [D47](0047-rollout-gated-by-evidence-pilot-25-pilot-100-then-all.md) | Rollout gated by evidence: pilot 25, pilot 100, then all users | Proposed | CA-2, CA-7, CP-4, SA-11, SC-5 |
| [D48](0048-code-provenance-federal-gitlab-source-of-truth.md) | Code provenance: federal GitLab is the source of truth | Proposed | CM-3, SA-10, SR-4 |
| [D49](0049-hostnames-and-tls-banner-login-provision-portal.md) | Hostnames and TLS layout | Proposed | AC-8, SC-8, SC-23, IA-3 |
| [D50](0050-dmz-haproxy-pair-forwarding-client-cert-header.md) | DMZ proxy is an HAProxy pair forwarding the client cert | Proposed | SC-7, SC-8, SC-23, AC-17 |
| [D51](0051-keycloak-authoritative-styx-limited-admin-client.md) | Keycloak is authoritative; Styx admin client is limited | Proposed | AC-2, AC-3, AC-5, AC-6 |
| [D52](0052-immutable-posix-uid-per-user.md) | Immutable POSIX UID per user | Proposed | AC-3, AC-2, IA-4 |
| [D53](0053-enterprise-profile-hard-disables-homelab-features.md) | Enterprise profile hard-disables homelab features | Proposed | CM-7, CM-6, IA-2, AC-3 |
| [D54](0054-profiles-on-cephfs-subvolumes.md) | Profiles on CephFS subvolumes | Proposed | CP-9, CP-10, CM-12 |
| [D55](0055-ceph-osd-reservations-and-throttled-recovery.md) | Ceph OSD reservations and throttled recovery | Proposed | SC-5, CP-2 |
| [D56](0056-styx-postgres-migration-alembic-leader-election-cnpg-roles.md) | Styx Postgres migration details | Proposed | CP-9, CP-10, SC-5, IA-5 |
| [D57](0057-own-rootless-selkies-pixelflux-base-image.md) | Own rootless Selkies and pixelflux base image | Proposed | CM-2, CM-6, SA-10, SR-3 |
| [D58](0058-selkies-maintained-patch-set.md) | Selkies maintained patch set | Proposed | SA-10, SI-7, AU-2, AC-11 |
| [D59](0059-notifications-portal-and-matrix-smtp-optional.md) | Notifications via portal and Matrix; SMTP optional | Proposed | AU-6, IR-4, SI-4 |
