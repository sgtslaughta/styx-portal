# Control matrix (NIST SP 800-53 Rev 5, Moderate baseline)

> Skeleton for the SSP and eMASS. Implementation statements are summaries and will be expanded per phase. PM family omitted (not in baseline). Covers key controls only, not all Moderate controls. Status is Planned for all rows. Risk acceptances R01-R06 are listed in design.md section 8. Inherited-Org marks organization-level (physical, personnel, training) items.

Responsibility: System = this project, Inherited-Org = provided by the organization, Hybrid = shared.

## AC - Access Control

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| AC-2 | Account Management | Keycloak directory; webhook provisioning, offboarding, review (ADR-0014, 0018, 0019, 0022, 0024) | System | Planned |
| AC-2(1) | Automated System Account Management | Webhook/SCIM-shaped provisioning (ADR-0019) | System | Planned |
| AC-2(3) | Disable Accounts | End-date, 35-day inactivity, remove-access flows (ADR-0022, 0024) | System | Planned |
| AC-2(4) | Automated Audit Actions | Account events to Elastic; Recently provisioned view (ADR-0023) | System | Planned |
| AC-3 | Access Enforcement | Keycloak roles, Styx authorization, Kyverno (ADR-0001, 0026) | System | Planned |
| AC-4 | Information Flow Enforcement | DLP policy, Cilium deny-all non-proxy egress, Squid category filtering (ADR-0038, 0040) | System | Planned |
| AC-5 | Separation of Duties | Admin role split (ADR-0026) | System | Planned |
| AC-6 | Least Privilege | Role model, group-manager scope, non-admin-only webhook (ADR-0020, 0026) | System | Planned |
| AC-7 | Unsuccessful Logon Attempts | Keycloak policy for break-glass accounts; CAC login via IdP (ADR-0015, 0025) | System | Planned |
| AC-8 | System Use Notification | USG banner before login (ADR-0027) | System | Planned |
| AC-11 | Device Lock | 15 min idle lock in Styx gateway; unlock by fresh TLS handshake proves card presence, not PIN entry; risk acceptance R02 (ADR-0039, 0058) | System | Planned |
| AC-12 | Session Termination | 2 h disconnect stop, 12 h max (ADR-0039) | System | Planned |
| AC-17 | Remote Access | DMZ proxy, CAC mTLS, monitored sessions (ADR-0012, 0045) | System | Planned |
| AC-20 | Use of External Systems | Managed clients, GCC High and upstream GitLab linkage (ADR-0019, 0043) | Hybrid | Planned |

## AT - Awareness and Training

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| AT-2 | Literacy Training and Awareness | Organizational security training; DLP user notices (ADR-0038) | Inherited-Org | Planned |
| AT-3 | Role-Based Training | Admin and help-desk role training (ADR-0026) | Inherited-Org | Planned |

## AU - Audit and Accountability

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| AU-2 | Event Logging | Event catalog incl. webhook, DLP (clipboard/file events as metadata only, never content), shadowing, egress hostnames (ADR-0020, 0038, 0044) | System | Planned |
| AU-3 | Content of Audit Records | Readable identity first.last plus EDIPI/card-UUID correlation; DLP records are metadata only (ADR-0016, 0038, 0044) | System | Planned |
| AU-4 | Audit Log Storage Capacity | Elastic 90 d hot / 1 y archive sizing (ADR-0044) | System | Planned |
| AU-5 | Response to Audit Logging Process Failures | Alerting on log shipping failure (ADR-0044) | System | Planned |
| AU-6 | Audit Record Review, Analysis, and Reporting | Daily digest, access reviews, Elastic (ADR-0023, 0024, 0044) | Hybrid | Planned |
| AU-8 | Time Stamps | Cluster NTP; time source from org (ADR-0044) | Hybrid | Planned |
| AU-9 | Protection of Audit Information | Auditor read-only role; Elastic access controls (ADR-0026, 0044) | Hybrid | Planned |
| AU-11 | Audit Record Retention | 1 y archive (ADR-0044) | System | Planned |
| AU-12 | Audit Record Generation | Styx, Keycloak, Squid hostnames, DLP metadata-only events; Selkies audit patch (ADR-0038, 0040, 0058) | System | Planned |

## CA - Assessment, Authorization, and Monitoring

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| CA-2 | Control Assessments | ADR and matrix evidence; assessor-driven (ADR-0010, 0013) | Hybrid | Planned |
| CA-3 | Information Exchange | Agreements for GCC High, upstream GitLab, cloud backup (ADR-0019, 0037) | Hybrid | Planned |
| CA-5 | Plan of Action and Milestones | Exceptions tracked in eMASS (ADR-0010, 0011) | Inherited-Org | Planned |
| CA-6 | Authorization | RMF ATO (ADR-0010) | Inherited-Org | Planned |
| CA-7 | Continuous Monitoring | SLO dashboards, scans, load gate (ADR-0044, 0047) | Hybrid | Planned |

## CM - Configuration Management

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| CM-2 | Baseline Configuration | Golden images, profiles in git (ADR-0003, 0028) | System | Planned |
| CM-3 | Configuration Change Control | Git-based review, image rollout (ADR-0003, 0030) | System | Planned |
| CM-6 | Configuration Settings | RKE2 hardening, image config; STIG exception (ADR-0007, 0011) | System | Planned |
| CM-7 | Least Functionality | Seat mode and homelab features hard-disabled with config test, minimal images (ADR-0004, 0028, 0053) | System | Planned |
| CM-8 | System Component Inventory | Component and SBOM inventory (ADR-0005, 0029) | System | Planned |
| CM-12 | Information Location | Homes, CephFS profiles, Ceph RGW archive; user-driven OneDrive moves (ADR-0034, 0035, 0054) | System | Planned |

## CP - Contingency Planning

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| CP-2 | Contingency Plan | HA design, availability targets (ADR-0006, 0008) | Hybrid | Planned |
| CP-4 | Contingency Plan Testing | Full-site restore test (phase 1), 200-session load-test gate (ADR-0037, 0047) | Hybrid | Planned |
| CP-6 | Alternate Storage Site | Encrypted CephFS-snapshot export to CUI-authorized cloud bucket (ADR-0037) | Hybrid | Planned |
| CP-7 | Alternate Processing Site | Not provided; exception R03 (ADR-0037) | Hybrid | Planned |
| CP-9 | System Backup | CNPG, Velero, home snapshots, offline-escrowed backup keys (ADR-0033, 0036, 0037, 0042) | System | Planned |
| CP-10 | System Recovery and Reconstitution | RTO 8 h restore procedures (ADR-0037) | System | Planned |

## IA - Identification and Authentication

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| IA-2 | Identification and Authentication (Organizational Users) | Keycloak smart-card-only login (CAC, PIV, PIV-I); break-glass exception R06 (ADR-0014, 0015, 0025) | System | Planned |
| IA-2(12) | Acceptance of PIV Credentials | CAC, PIV and PIV-I (PIV Authentication cert only); DoD roots + Federal Common Policy CA; OCSP + CRL mirror (ADR-0015, 0016, 0017, 0041) | System | Planned |
| IA-3 | Device Identification and Authentication | mTLS client cert for webhook (ADR-0020) | System | Planned |
| IA-4 | Identifier Management | EDIPI (CAC) or card UUID (PIV/PIV-I) bound at first login, immutable username (ADR-0016, 0018) | System | Planned |
| IA-5 | Authenticator Management | PKI via DoD and federal CAs; break-glass and token rotation; OpenBao auto-unseal, offline escrow (ADR-0015, 0020, 0025, 0042) | Hybrid | Planned |
| IA-5(2) | Public Key-Based Authentication | Certificate validation for CAC/PIV/PIV-I chains, OCSP + CRL mirror (ADR-0015, 0017) | System | Planned |
| IA-8 | Identification and Authentication (Non-Organizational Users) | Not planned; no external users in v1 (ADR-0001, 0015) | System | Planned |
| IA-12 | Identity Proofing | Approval workflow; Styx checks asserted approver is a group manager, cannot verify M365 approval, D23 review is the real control; R04 (ADR-0018, 0020, 0021, 0023) | Hybrid | Planned |

## IR - Incident Response

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| IR-4 | Incident Handling | Alerting to ops and security officer (ADR-0023, 0025, 0044) | Hybrid | Planned |
| IR-5 | Incident Monitoring | Elastic SIEM (ADR-0044) | Hybrid | Planned |
| IR-6 | Incident Reporting | Organizational reporting chain | Inherited-Org | Planned |

## MA - Maintenance

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| MA-2 | Controlled Maintenance | Maintenance banner; one monthly announced evening window excluded from 99.9 % (ADR-0008, 0046) | Hybrid | Planned |
| MA-4 | Nonlocal Maintenance | Admin access via break-glass and roles (ADR-0025, 0026) | System | Planned |

## MP - Media Protection

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| MP-6 | Media Sanitization | Scratch volume reclaim after 7 days stopped, object-lock cold tier, disk disposal (ADR-0035) | Hybrid | Planned |
| MP-7 | Media Use | Download-out off, print off (ADR-0038) | System | Planned |

## PE - Physical and Environmental Protection

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| PE-3 | Physical Access Control | Hosting facility controls (ADR-0006) | Inherited-Org | Planned |
| PE-6 | Monitoring Physical Access | Hosting facility (ADR-0006) | Inherited-Org | Planned |

## PL - Planning

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| PL-2 | System Security and Privacy Plans | Repo docs feed SSP (ADR-0010, 0013) | Hybrid | Planned |
| PL-4 | Rules of Behavior | Organizational; banner reinforces (ADR-0027) | Inherited-Org | Planned |

## PS - Personnel Security

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| PS-3 | Personnel Screening | Organizational | Inherited-Org | Planned |
| PS-4 | Personnel Termination | Offboarding flows (ADR-0022) | Hybrid | Planned |
| PS-5 | Personnel Transfer | Group changes and access review (ADR-0024) | Hybrid | Planned |

## RA - Risk Assessment

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| RA-3 | Risk Assessment | Organizational risk assessment with ADR input (ADR-0010) | Hybrid | Planned |
| RA-5 | Vulnerability Monitoring and Scanning | Trivy, Harbor, image rebuilds (ADR-0029, 0030) | System | Planned |

## SA - System and Services Acquisition

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| SA-3 | System Development Life Cycle | Single codebase, CI; federal GitLab source of truth (ADR-0003, 0028, 0048) | System | Planned |
| SA-4 | Acquisition Process | Component and license rule; accepted costs listed (ADR-0005) | Hybrid | Planned |
| SA-9 | External System Services | GCC High, upstream GitLab, cloud bucket (ADR-0019, 0037) | Hybrid | Planned |
| SA-10 | Developer Configuration Management | Git, signed builds (ADR-0003, 0029) | System | Planned |
| SA-11 | Developer Testing and Evaluation | Load test and security testing (ADR-0047) | System | Planned |

## SC - System and Communications Protection

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| SC-5 | Denial-of-Service Protection | DMZ proxy limits, resource caps (ADR-0009, 0031) | System | Planned |
| SC-7 | Boundary Protection | HAProxy DMZ pair, Cilium, Squid; SC-7(5) tailored, R01 (ADR-0007, 0012, 0040, 0050) | System | Planned |
| SC-7(5) | Deny by Default - Allow by Exception | Tailored: internet allowed with category blocking; Cilium denies all non-proxy egress; risk acceptance R01 (ADR-0040) | System | Planned |
| SC-8 | Transmission Confidentiality and Integrity | TLS at DMZ, separate banner/login/provision/portal hosts, mTLS webhook (ADR-0012, 0020, 0049) | System | Planned |
| SC-10 | Network Disconnect | Idle and disconnect timeouts (ADR-0039) | System | Planned |
| SC-12 | Cryptographic Key Establishment and Management | OpenBao PKI, auto-unseal, Shamir recovery split, offline escrow (ADR-0042) | System | Planned |
| SC-13 | Cryptographic Protection | Non-FIPS exception recorded (ADR-0011) | System | Planned |
| SC-23 | Session Authenticity | OIDC sessions, CSRF protections (ADR-0043) | System | Planned |
| SC-28 | Protection of Information at Rest | Ceph, backups encryption (ADR-0033, 0037, 0042) | System | Planned |

## SI - System and Information Integrity

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| SI-2 | Flaw Remediation | Nightly rebuild, 24 h critical-CVE recycle (ADR-0029, 0030) | System | Planned |
| SI-3 | Malicious Code Protection | To be decided in phase 3 | System | Planned |
| SI-4 | System Monitoring | Elastic, Prometheus (ADR-0044) | System | Planned |
| SI-7 | Software, Firmware, and Information Integrity | cosign and Kyverno (ADR-0029) | System | Planned |
| SI-10 | Information Input Validation | Webhook strict schema (ADR-0020) | System | Planned |
| SI-12 | Information Management and Retention | Age-off to Ceph RGW cold storage with self-restore (ADR-0035) | Hybrid | Planned |

## SR - Supply Chain Risk Management

| Control | Title | Implementation | Responsibility | Status |
|---|---|---|---|---|
| SR-3 | Supply Chain Controls and Processes | Signed allowlisted images, SBOM (ADR-0029) | System | Planned |
| SR-4 | Provenance | SBOM, signatures, federal GitLab as source of truth (ADR-0029, 0048) | System | Planned |
| SR-11 | Component Authenticity | cosign verification (ADR-0029) | System | Planned |
