# Persistent profiles + GPU at launch — implementation plan

Spec: `docs/superpowers/specs/2026-10-26-persistent-profiles-design.md` (read it, incl. addendum).
Branch `feat/profiles-gpu` off origin/main. TDD, one semantic commit per task, trailer
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. No push.
Backend gate: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`.
Frontend gate: `cd frontend && npm run build` (+ `npx vitest run` if tests exist for touched files).
Do NOT grow `routers/instances.py` (887 lines) by more than ~40 lines net: new logic goes in
`app/services/profiles.py` / `app/services/gpu_access.py`.

## Backend

### Task 1 — schema + migrations
- `models.py`: `ServiceTemplate.profile_mount: str | None = None`; `Instance.profile_volume: str | None = None`,
  `Instance.gpu: bool | None = None` (None = legacy → use template.gpu_enabled), `Instance.notice: str | None = None`;
  `Group.allow_gpu: bool = False`; new table
  `UserProfile(__tablename__="user_profiles")`: `user_id` (fk users.id, pk), `template_id` (fk service_templates.id, pk),
  `volume_name: str`, `created_at`.
- `database.py:_run_migrations` list: `("service_templates","profile_mount","TEXT")`,
  `("instances","profile_volume","TEXT")`, `("instances","gpu","BOOLEAN")`, `("instances","notice","TEXT")`,
  `("groups","allow_gpu","BOOLEAN DEFAULT 0")`. (New table is created by `create_all`.)
- `schemas.py`: `profile_mount: str | None = None` on `TemplateCreate` + `TemplateUpdate` with a validator reusing
  the mount check from `template_validation.validate_volumes` (extract it into `validate_mount(m)` there).
  `InstanceCreate`: `use_profile: bool = False`, `use_gpu: bool = True`.
  Add `profile_mount`, `profile_volume`, `gpu`, `notice` to the instance/template response schemas if those are
  explicit (grep); `allow_gpu` to the group response.
- `routers/templates.py:_TEMPLATE_UPDATE_FIELDS`: add `"profile_mount"`.
- `templates/xfce-desktop.json`: `"profile_mount": "/config"` (seeding is insert-only; fine).
- Tests: migration test adds the columns; template create/update round-trips `profile_mount`; bad mount → 422.

### Task 2 — `app/services/profiles.py`
```python
ACTIVE = ("running", "starting", "pulling")
def profile_volume_name(user_id, template_name) -> str:
    return k8s_name(f"profile-{user_id}-{template_name}")   # from k8s_routes; lowercase, hashed if >63
async def ensure_profile(session, user_id, template) -> str   # upsert UserProfile row, return volume name
async def profile_in_use(session, volume, exclude_instance_id=None) -> Instance | None
    # another Instance with profile_volume == volume and status in ACTIVE
async def delete_profile(session, runtime, user_id, template_id) -> None
    # 404 if no row; 409 if in use; runtime.remove_volume (ignore not-found); delete row
def mounts_for(template, instance) -> list[tuple[str, str]]   # [(volume_name, mount)]
    # template volumes via resolve_volume_name(name, instance.id), SKIPPING the one whose mount ==
    # template.profile_mount when instance.profile_volume is set; plus (instance.profile_volume, profile_mount)
```
- Runtime `create_volume(name, size=None)`: Docker ignores size; k8s passes it to `pvc(name, ns, size=None)`
  (default `INSTANCE_VOLUME_SIZE`). Setting `PROFILE_VOLUME_SIZE: str = "20Gi"` in `config.py`; profile volumes
  are created with it. Update the conftest MagicMock `create_volume.side_effect` to accept `size`.
- Tests: name is deterministic, lowercase, ≤63; in_use excludes self and stopped; mounts_for swaps the mount.

### Task 3 — wire profiles into instances
- `create_instance`: if `body.use_profile`: 422 if `template.profile_mount` is empty; vol = `ensure_profile(...)`;
  409 `"Your <template.display_name> profile is in use by <other.name>"` if `profile_in_use(vol)`;
  set `instance.profile_volume = vol`.
- `_launch_instance_background` and `_build_and_start_container`: replace the volume loops with `mounts_for`;
  `instance.volume_names` = only the non-profile names (profile never in it). Profile volume created with
  `size=Settings().PROFILE_VOLUME_SIZE`.
- `start_instance`, `recreate_instance`: same 409 check (exclude self) before starting.
- Delete: ALWAYS remove `instance.volume_names` (ignore the `remove_volumes` query param, keep it accepted for old
  clients); never touch `profile_volume`. Wrap each `remove_volume` in try/except → log warning (volume may be gone).
- New router `app/routers/profiles.py` (register in main.py):
  - `GET /api/profiles` → current user's `[{template_id, template_name, display_name, volume_name, in_use}]`
  - `DELETE /api/profiles/{template_id}` → own profile reset (204)
  - `GET /api/users/{user_id}/profiles`, `DELETE /api/users/{user_id}/profiles/{template_id}` → `require_admin`
  Audit-log deletes like other routers do.
- Tests (test_instances_api style with `shared_docker`): launch with profile mounts `profile-…` at profile_mount
  and template volume at that mount is NOT created; 2nd profile launch while first running → 409; after stop → ok;
  delete removes volume_names and not the profile; profile API list/delete/409-in-use/admin-only.

### Task 4 — GPU at launch (`app/services/gpu_access.py`)
```python
async def user_may_use_gpu(session, user) -> bool   # admin, or any of user's groups has allow_gpu
```
- `create_instance`: `instance.gpu = template.gpu_enabled and body.use_gpu and await user_may_use_gpu(...)`.
- Where the launch/build passes `gpu_enabled`/`gpu_count` to `create_container`: use
  `want = instance.gpu if instance.gpu is not None else template.gpu_enabled`; if `want` and not
  `runtime.gpu_free(template.gpu_count)` → `want = False`, `instance.notice = "No GPU free, running on CPU"`;
  else `instance.notice = None`.
- `DockerManager.gpu_free(n) -> True`. `K8sInstanceRuntime.gpu_free(n)`: GET
  `/api/v1/namespaces/{ns}/resourcequotas/instances`; free = hard − used of `requests.amd.com/gpu`
  (missing quota/key → True); return `free >= n`. Comment: `# ponytail: counts Styx quota only; non-Styx GPU pods unseen`.
- `deploy/k8s/instances.yaml` Role: add core `resourcequotas` verbs `[get]`.
- Groups: `PATCH /api/groups/{group_id}` body `{allow_gpu: bool}` (+ optional description), require_admin, audit.
- `/api/auth/me` response: add `can_use_gpu: bool` (via `user_may_use_gpu`). Find the me schema.
- Tests: member without group → gpu False even if asked; member in allow_gpu group → True; admin → True;
  use_gpu=False → False; non-GPU template → False; k8s gpu_free math (quota used 3/3 → False, 2/3 → True,
  no quota → True); fallback sets notice and passes gpu_enabled=False to create_container.

## Frontend (after backend is green)

### Task 5
- `lib/types.ts` + `api/client.ts`: new fields (`profile_mount`, `profile_volume`, `gpu`, `notice`, `allow_gpu`,
  `can_use_gpu`, `use_profile`, `use_gpu`); `getMyProfiles`, `deleteMyProfile`, `getUserProfiles`,
  `deleteUserProfile`, `updateGroup`. `deleteInstance` stops sending `remove_volumes`.
- `launch-modal.tsx`: checkbox "Use my persistent profile" (shown when template.profile_mount) and
  "Use GPU" (shown when template.gpu_enabled && me.can_use_gpu, default on). Send `use_profile`, `use_gpu`.
  Show the API's 409 detail in the existing error display.
- `action-bar.tsx:129` dialog text → "Instance data is deleted. Your persistent profile (if used) is kept."
  Same wording anywhere else that says volumes are kept (instance-grid bulk, metrics-sessions).
- Instance card: show `notice` as a small warning line if set.
- Template builder `builder/sections/storage.tsx`: "Persistent profile path" text input → `profile_mount`
  (wire through `use-launch-config.ts` state + `buildTemplateData`).
- `groups-panel.tsx`: "Allow GPU" toggle per group → `updateGroup`.
- `users-panel.tsx` dropdown: "Profiles…" opens a small dialog (pattern: `user-groups-dialog.tsx`) listing the
  user's profiles with Delete. Keep users-panel < 500 lines (dialog in its own file).
- Self-service: a "My profiles" list with "Reset" — put it where the user's own settings live (grep for the
  change-password UI) in its own component file.
