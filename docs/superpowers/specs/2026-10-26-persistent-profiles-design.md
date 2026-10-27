# Persistent profiles (Kasm-style) — design

## Intent
Instance data is disposable by default. A user who wants their settings to follow them
(bookmarks, logins, app config) opts into a **persistent profile**: a per-user volume that every
instance of the same template mounts. Admins decide which templates offer it. Model: Kasm
persistent profiles.

## Behaviour
- **No profile (default):** the instance's own volumes live as long as the instance. Stop/start,
  idle-stop and recreate keep them; **delete always removes them**. The "keep volumes" choice on
  delete goes away.
- **With profile:** launch dialog shows "Use my persistent profile" (only when the template allows
  it). The profile volume is mounted at the template's profile path instead of a per-instance
  volume. Deleting the instance never deletes the profile.
- **One at a time:** launching/starting a second instance that uses the same profile while another
  is running/starting → 409 "Your <template> profile is in use by <instance>". Stop it first.
- Same on k8s and compose.

## Admin configuration
- Template field `profile_mount: str | None` (e.g. `/config`). Set = template offers profiles.
  Edited in the template form like the other fields; validated like volume mounts.
- Settings: `PROFILE_VOLUME_SIZE` (k8s PVC size, default `20Gi`); storage class reuses
  `INSTANCE_STORAGE_CLASS`.
- Admin can list and delete a user's profiles (API + a small section on the user's admin row).
  A user can delete ("reset") their own profile for a template.

## Storage (decided)
- One volume per (user, template): name `profile-<user_id>-<template_name>` (k8s: PVC in
  `styx-instances`, RWO; compose: named Docker volume). *My call:* the owner picked "one volume,
  subfolder per template"; separate volumes give the same result but let a user run chrome and
  xfce at the same time (an RWO volume can't attach to pods on two nodes).
- `Instance.profile_volume: str | None` records it; never part of `volume_names`, so no delete path
  touches it.
- Template volumes whose mount equals `profile_mount` are skipped for profile instances.

## Non-goals
- Profile sync/upload to S3, size quotas per user, per-group enablement (later if wanted).
- Migrating existing per-instance volumes into profiles.

## Cleanup
- Existing orphan PVC `43cec342-…-config` (deleted chrome) is removed by hand once shipped.

## Left to the builder
Endpoint shapes, migration of the two new columns (existing lightweight migration pattern),
frontend placement, tests (fake runtime / mocked Docker as today). Keep files < 500 lines —
put profile logic in `services/profiles.py`, not in `routers/instances.py` (already 887).

# Addendum: GPU at launch (owner, 2026-10-26)
- Template `gpu_enabled` now means "GPU supported". Launch dialog shows "Use GPU" (default on)
  when the template supports it AND the user may use GPU.
- Who may: admins always; others if any of their groups has `allow_gpu = true` (new Group
  column, toggled on the groups admin page).
- Request without permission or for a non-GPU template → GPU silently off (no error).
- `Instance.gpu: bool` records the choice; start/recreate reuse it.
- **No free GPU → fall back to CPU** and set a notice on the instance ("No GPU free, running
  on CPU"). k8s: free = ResourceQuota `instances` `hard - used` for `requests.amd.com/gpu`
  (backend Role gets get on resourcequotas). *My call:* quota is the only GPU consumer we track;
  GPUs used by non-Styx pods are not counted (ponytail ceiling; node-allocatable scan if that
  changes). Compose: GPU is shared /dev/dri, always "free".
