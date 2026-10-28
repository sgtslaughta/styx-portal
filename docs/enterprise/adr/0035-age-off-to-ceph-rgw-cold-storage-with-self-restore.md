# ADR-0035: Age-off to Ceph RGW cold storage with user self-restore

- Status: Proposed
- Date: 2026-10-28
- Decision ID: D35
- Related controls: MP-6, SI-12, CM-12, SC-28

## Context

Limited storage requires lifecycle handling of stale data while retaining CUI properly.

Source: docs/enterprise/design.md section 5.

## Decision

Home files untouched 90 days get a 14-day notice, then move automatically to on-prem Ceph RGW cold storage (object lock, lifecycle); users self-restore from the portal. Users may move files to OneDrive (GCC High) themselves from the browser inside their desktop; egress allows GCC High OneDrive. There is no automatic OneDrive transfer (no service account, no live token). Profiles unused 60 days are deleted after notice. With the daily stop, per-instance scratch volumes are reclaimed after 7 days stopped; persistent data belongs in home/profile. Users may archive anytime.

## Alternatives considered

Entries beyond those recorded in design.md are the obvious options, not documented discussion.

- Automatic archive to OneDrive - needs a service account or stored token, neither available.
- Silent deletion - data loss.
- Keep forever - capacity exhaustion.

## Consequences

Positive:

- Controlled storage lifecycle fully on-prem and automatic.
- Users can recover their own files.
- No stored M365 credentials.

Negative:

- Manual OneDrive moves from inside the desktop are a user-driven path around download-out-off (D38); accepted because GCC High is an authorized CUI store.
- Files of departed users need a defined path.
- Ceph capacity must include the cold tier.

Follow-up work:

- RGW object-lock and lifecycle config and portal restore UI in phase 5.
