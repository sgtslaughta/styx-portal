# Admin-gated Docker-in-Docker (DinD) Templates — Design

**Date:** 2026-06-02
**Status:** Approved

## Goal

Let the custom desktop image (and any template) run a real, isolated Docker
daemon inside the instance — true Docker-in-Docker — gated so only admins can
author DinD-enabled templates.

## Decisions (user-locked)

1. **Isolation model:** True DinD via privileged container + the linuxserver
   selkies base image's bundled dockerd. Not host-socket mount, not rootless.
2. **Control plane:** Boolean `dind` flag on `ServiceTemplate`. Authoring a DinD
   template (create/update with `dind=true`) requires `role == "admin"`.
   Launching such a template is allowed for normal users.
3. **Storage:** Persist nested images — per-instance named volume mounted at
   `/var/lib/docker` (unlocks overlay2 driver + survives restarts).

## Background / why it works

- `ghcr.io/linuxserver/baseimage-selkies` ships docker binaries and a DinD s6
  init service. It auto-starts when the container is `--privileged` **unless**
  `START_DOCKER=false`.
- The desktop Dockerfile (`images/desktop/Dockerfile`) already sets
  `ENV START_DOCKER=false`. So privileged alone is inert — safe default.
- Backend flips it on per-launch by injecting `START_DOCKER=true` only when the
  template's `dind` flag is set. No Dockerfile change required.
- Nested DinD defaults to slow fuse-overlayfs; mounting a Linux-host volume at
  `/var/lib/docker` enables overlay2 and persists pulled images.

## Components

### 1. Image — no change
Keep `ENV START_DOCKER=false`. Base already provides dockerd. Zero edits.

### 2. Data model — `backend/app/models.py`
Add to `ServiceTemplate`:
```python
dind: bool = False
```
Migration in `backend/app/database.py` `_run_migrations` list:
```python
("service_templates", "dind", "BOOLEAN"),
```

### 3. Container creation — `docker_manager.create_container`
Add param `dind: bool = False`. When true:
- `privileged = True`
- inject env `START_DOCKER=true` (merged into `environment`)
- mount caller-supplied docker-storage volume at `/var/lib/docker`

Existing `privileged` param stays; `dind=True` forces it true regardless.

### 4. Instance lifecycle — `backend/app/routers/instances.py`
Both create paths (`_build_and_start_container` ~L59,
`_launch_instance_background` ~L127):
- pass `dind=template.dind`
- when `template.dind`, append a per-instance named volume
  `selkies-{instance_id}-dockerstore` bound to `/var/lib/docker` (mode rw),
  and add its name to `instance.volume_names`.

Reusing `instance.volume_names` means the existing create-on-launch and
remove-on-delete volume lifecycle persists and cleans the docker store for free.

### 5. Authorization — `backend/app/routers/templates.py`
In `create_template` and `update_template`, when the incoming body sets
`dind=True`:
```python
if body.dind and user.role != "admin":
    raise HTTPException(403, "DinD templates require admin")
```
Note: `create_template` currently performs no role check; this is the gate.
Schemas `TemplateCreate` / `TemplateUpdate` (`backend/app/schemas.py`) gain
`dind: bool = False`.

### 6. Frontend
Template create/edit form: a `DinD` toggle, rendered/enabled only when
`user.role === 'admin'`, with privileged-warning helptext. Optional DinD badge
on the template card.

### 7. Tests
- `create_container(dind=True)` → kwargs include `privileged=True`,
  `environment["START_DOCKER"]=="true"`, and `/var/lib/docker` mount.
- non-admin create/update with `dind=true` → 403; admin → success.
- launching a dind template appends `selkies-{id}-dockerstore` to
  `volume_names` and it is removed on instance delete.

## Security

`--privileged` is host-root-equivalent: a user inside a DinD desktop can reach
the host. Mitigations: admin-only authoring gate, per-instance volume isolation,
and the project's single-host / trusted-user deployment posture (design
decision #2 in CLAUDE.md). Document the risk in the template form helptext.

## Out of scope (YAGNI)

- Rootless / sysbox runtime.
- Host-socket sharing mode.
- Quotas on nested image storage.
- Per-user DinD authoring (admin-only for now).
