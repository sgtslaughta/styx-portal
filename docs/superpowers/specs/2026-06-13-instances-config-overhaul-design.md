# Instances Configuration Overhaul — Design

Date: 2026-06-13
Status: Approved (design), pending implementation plan

## Goal

Polish overhaul of instance configuration. Two-tier experience:

- **Easy mode** — for linuxserver.io / desktop templates. Zero-to-minimal config; sensible
  defaults from the template/registry "just work". User supplies a name and launches.
- **Advanced mode** — full template tweaking with polished, type-appropriate controls
  (sliders, selects, toggles, key/value editors), tooltips throughout.
- **Custom templates** — create from clone / registry image / scratch. Admin- or
  user-defined; owners can share to all users. Same builder UI; admins additionally
  unlock high-risk docker options.

Everything a user could do manually with `docker run` (pragmatic high-value subset) is
reachable from the UI. Ports are proxied through Traefik (never raw host-published).
High-risk options are admin-gated, enforced server-side.

## Scope decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Backend docker-option surface | **Pragmatic tier** — high-value options now; exotic ones behind a 🔒 raw escape hatch |
| High-risk option access | **Admin-only gate** — non-admins see locked controls; admins toggle. Enforced server-side, not just UI |
| Multi-port remote access | **Path prefixes** — primary port stays subdomain; extra ports at `host/p/<slug>` via Traefik stripprefix |
| Easy-mode launch layout | **Layout B** — left "what you get" summary, right minimal form (name + address + Launch), "Switch to Advanced" toggle |
| Advanced builder layout | **Layout A** — left section rail + right panel |
| Advanced builder placement | **Both** — inline in launch modal + dedicated full-page route. One shared component |
| Custom-template entry points | **Clone existing**, **From registry image**, **From scratch** |
| Template sharing | **Owner shares to all** — `shared` flag on user-owned templates; admin can unshare/remove any |

## Non-goals

- Raw host port publishing in the UI (would bypass Traefik auth). All ingress via Traefik.
- Exotic docker options as first-class fields: `network_mode` (host/container), `sysctls`,
  arbitrary host bind mounts for non-admins. These are reachable only via the admin-only
  `extra_docker_args` escape hatch, allowlist-validated.
- Per-instance approval queue (the "tiered with audit" model was declined).
- Second-screen / multi-display changes (unrelated, upstream-limited).

---

## 1. Data model

### 1.1 `ServiceTemplate` new fields

All optional with safe defaults so existing templates and the seed JSON stay valid.

| Field | Type | Default | Gate | Notes |
|---|---|---|---|---|
| `shared` | bool | `False` | owner/admin | User-owned template visible to all users (read-only to non-owners) |
| `restart_policy` | str | `"no"` | safe | enum: `no` / `on-failure` / `unless-stopped` / `always` |
| `read_only_rootfs` | bool | `False` | safe | maps to `read_only=True` |
| `tmpfs` | list[str] | `[]` | safe | mount paths, e.g. `/tmp` (size optional per entry) |
| `extra_hosts` | dict[str,str] | `{}` | safe | host→IP for `extra_hosts` |
| `ulimits` | list[dict] | `[]` | safe | `{name, soft, hard}` |
| `extra_ports` | list[dict] | `[]` | safe | `{container_port:int, label:str, slug:str, strip_prefix:bool}` proxied via path prefix |
| `entrypoint` | list[str] \| None | `None` | 🔒 admin | overrides image entrypoint |
| `command` | list[str] \| None | `None` | 🔒 admin | overrides image cmd |
| `devices` | list[str] | `[]` | 🔒 admin | `/dev/x:/dev/x` passthrough |
| `privileged` | bool | `False` | 🔒 admin | promoted from a docker_manager arg to a template field |
| `extra_docker_args` | dict | `{}` | 🔒 admin | raw escape hatch, allowlist-validated |

LSIO helpers (`puid`, `pgid`, `tz`) are **not** new columns — they are surfaced as
first-class UI controls that read/write `env_vars["PUID"]`, `["PGID"]`, `["TZ"]`.

### 1.2 Migration

SQLite: additive columns with defaults. Add an idempotent column-add step in
`database.py` startup (matches existing `error_message` migration approach). Seed JSON
templates remain valid (new fields default). No backfill needed.

### 1.3 Schema updates (`schemas.py`)

`TemplateCreate` / `TemplateUpdate` gain the new fields. `_TEMPLATE_UPDATE_FIELDS`
allowlist in `routers/templates.py` extended with the safe fields and (admin-checked)
risk fields.

---

## 2. Backend — docker option pass-through

### 2.1 `docker_manager.create_container`

Extend signature + kwargs mapping (docker-py):

| Template field | docker-py kwarg |
|---|---|
| `restart_policy` | `restart_policy={"Name": ..., "MaximumRetryCount": n}` |
| `read_only_rootfs` | `read_only` |
| `tmpfs` | `tmpfs={path: ""}` |
| `extra_hosts` | `extra_hosts` |
| `ulimits` | `ulimits=[Ulimit(...)]` |
| `devices` | `devices` (merged with GPU `/dev/dri`) |
| `entrypoint` | `entrypoint` |
| `command` | `command` |
| `privileged` | `privileged` (existing) |
| `extra_docker_args` | merged last, allowlist-validated |

Keep existing GPU / dind / cap / security_opt logic. `privileged=True` still skips
`cap_add`/`cap_drop` (docker rejects them together) — unchanged.

### 2.2 `extra_docker_args` allowlist

Validation lives in a small `services/docker_args.py` helper, unit-tested.

- **Rejected for everyone** (escape/abuse): `network_mode` in {`host`, `container:*`},
  `pid_mode=host`, `ipc_mode=host`, `userns_mode=host`, `cap_add` (use the dedicated
  field), `binds`/`volumes` with host source paths (named volumes only), `ports`
  (raw host publish — forbidden, Traefik only).
- **Admin-only** (already behind the 🔒 gate that exposes `extra_docker_args` at all):
  `sysctls`, `cgroup_parent`, `runtime`, `device_cgroup_rules`, `security_opt`
  additions, `tmpfs` extras.
- **Allowed**: `labels` (merged, cannot override `traefik.*` keys), `hostname`,
  `dns`, `dns_search`, `stop_signal`, `stop_timeout`, `working_dir`, `init`.

Unknown kwargs are rejected (allowlist, not denylist). Validation returns a structured
error surfaced to the UI.

### 2.3 Authorization (server-side, `routers/templates.py`)

On create/update, if the payload sets any 🔒 field (`devices`, `entrypoint`, `command`,
`privileged`, `extra_docker_args`, plus existing `dind`/`cap_add`/`security_opt`) and the
caller is not admin → `403`. This is the source of truth; the UI lock is convenience only.

`shared` toggle: only the owner or an admin may set it. Setting `shared=True` requires no
admin (it shares only the safe surface a non-admin could build anyway).

### 2.4 Template visibility query

`list_templates` for non-admin:
`owner_id == user.id OR owner_id IS NULL OR shared == True`.
Admins see all. Response includes `owner_id`/`shared` so the UI can badge "shared by X"
and gate edit vs launch-only.

---

## 3. Ports & remote access

### 3.1 Primary port (unchanged)

`internal_port` + `internal_protocol` → subdomain router `Host(\`{subdomain}.{domain}\`)`
with auth middleware. WebRTC/WebSocket streaming keeps a clean host. No change.

### 3.2 Extra ports (path prefix)

Each `extra_ports` entry generates an additional Traefik router + service that **nests
under the instance's existing primary route**, so it works in every deploy mode:

- **Direct/subdomain mode** (primary = `Host(\`{subdomain}.{domain}\`)`):
  rule `Host(\`{subdomain}.{domain}\`) && PathPrefix(\`/p/{slug}\`)`.
- **LAN/IP mode** (primary already path-based `/i/{subdomain}`):
  rule nests the prefix → `PathPrefix(\`/i/{subdomain}/p/{slug}\`)`.
- Service load-balances to the container's `container_port`.
- Optional `stripprefix` middleware (the `/p/{slug}` segment stripped) when
  `strip_prefix=true`.
- Same auth middleware as the primary route — extra ports are never unauthenticated.
- `slug` must be unique within a template and URL-safe (validated on save).

`route_writer.refresh_routes_from_db` reads `template.extra_ports` for each running
instance and emits these routers. `build_routes_config` gains the per-port loop.

### 3.3 UI guidance

The Ports & Network section warns: a path-prefixed app must support a base-URL/subpath
setting (else absolute asset URLs break). Where the registry/image is known to need an
env var (e.g. a `BASE_URL`/`SUBFOLDER`), show the hint inline. `strip_prefix` defaults
on; toggle off for apps that expect the full path.

---

## 4. Frontend

Stack in place: React 19, shadcn/ui (Radix + Tailwind v4), TanStack Query v5,
framer-motion, lucide, sonner.

### 4.1 Easy mode (launch modal, layout B)

Default view of `launch-modal.tsx`:

- Left pane "What you get": icon, display name, resource chips (GPU/RAM/CPU), storage
  mounts, "streams at `{subdomain}.{domain}`", "auth on".
- Right pane: **Name**, **Address** (subdomain, auto-derived + editable), **Launch**.
- "Switch to Advanced →" swaps the body to the advanced builder in place (state preserved
  via the existing `use-launch-config` hook).

### 4.2 Advanced builder (layout A) — shared component

New `templates/builder/` directory. One `<TemplateBuilder>` with a left section rail and
a right panel. Each section is its own file (keep <500 lines):

```
templates/builder/
  template-builder.tsx        orchestrator + section rail
  sections/basics.tsx         name, image, icon, display name, description, category, tags
  sections/resources.tsx      memory/cpu/shm sliders, gpu toggle+count, restart policy, ulimits
  sections/storage.tsx        volumes (repeatable), tmpfs, read-only rootfs
  sections/ports-network.tsx  primary port+protocol, extra ports (repeatable), extra_hosts, path-prefix guidance
  sections/environment.tsx    env editor + LSIO helpers (PUID/PGID/TZ), reuse env-editor.tsx
  sections/security.tsx       🔒 caps, security_opt, privileged, devices, dind
  sections/raw-docker.tsx     🔒 entrypoint, command, extra_docker_args (validated)
  controls/                   shared typed controls (see 4.3)
```

Mounted two ways:
- **Inline** inside `launch-modal.tsx` (advanced view) — for tweak-then-launch.
- **Full page** at routes `/templates/new` and `/templates/:id/edit` — for authoring/
  sharing, with Save / Save & Share / Save as new.

### 4.3 Control language (shared `controls/`)

| Control | Used for | Behavior |
|---|---|---|
| `SliderInput` | memory, cpu, shm, gpu_count, ulimit values | range slider + synced typed box + unit suffix |
| `EnumSelect` | restart policy, protocol, timeout action | shadcn Select |
| `ToggleField` | gpu, read-only rootfs, privileged, tls_skip_verify, dind | shadcn Switch |
| `KeyValueEditor` | env, extra_hosts, labels | existing `env-editor.tsx` generalized |
| `RepeatableRows` | volumes, extra ports, devices, ulimits, tmpfs | add/remove rows, per-field validation |
| `Tooltip` (ⓘ) | every field | shadcn tooltip; concise what + why + example |
| `LockedField` | any 🔒 field for non-admin | wraps control disabled + lock badge + "requires admin" tooltip |

`useAuth`/role from context drives `LockedField`. Lock is cosmetic; server enforces.

### 4.4 Custom template creation

Entry points (a "New template" menu on the templates page):
- **Clone existing** — preselect a visible template, builder prefilled, name cleared.
- **From registry image** — image search/paste, prefill ports/env from registry metadata
  (reuse existing registry-import path in `use-launch-config`).
- **From scratch** — empty builder.

Save actions: **Save** (owner), **Save & Share** (sets `shared=true`), **Save as new**.
Template grid badges shared templates ("shared by X"); non-owner sees launch-only (no edit).

---

## 5. Testing

### Backend (pytest, mocked docker)
- Migration adds columns idempotently; existing seed templates load.
- Each new template field maps to the correct docker-py kwarg in `create_container`.
- `docker_args` allowlist: rejected kwargs (host network, raw ports, host binds) → error;
  allowed kwargs pass; unknown kwargs rejected.
- Admin gate: non-admin setting any 🔒 field → 403; admin succeeds.
- `shared` visibility: non-admin sees own + global + shared; cannot edit non-owned shared.
- `route_writer`: `extra_ports` produce path-prefix routers with stripprefix + auth
  middleware; primary subdomain route unchanged.

### Frontend (vitest/RTL)
- Easy↔Advanced toggle preserves config state.
- Each control renders for its type; SliderInput slider/box stay synced.
- `LockedField` disabled + tooltip for non-admin; enabled for admin.
- Clone / registry / scratch flows seed the builder correctly.
- Builder produces a correct create/update payload (incl. extra_ports, LSIO env helpers).

### Quality gates
- `ruff check` clean; `pytest -v` green; `tsc` clean.
- Files kept <500 lines (builder split per section).

---

## Open defaults (chosen, change on request)

- Path-prefix base: `/p/<slug>`.
- `extra_docker_args` allowlist as enumerated in §2.2.
- `strip_prefix` defaults **on** per extra port.

## Affected files (indicative)

- `backend/app/models.py` — `ServiceTemplate` fields
- `backend/app/schemas.py` — Create/Update schemas
- `backend/app/database.py` — column-add migration
- `backend/app/routers/templates.py` — allowlist + admin gate + visibility + shared
- `backend/app/routers/instances.py` — pass new fields to docker_manager
- `backend/app/services/docker_manager.py` — kwarg mapping
- `backend/app/services/docker_args.py` — **new** allowlist validator
- `backend/app/services/route_writer.py` + `traefik_labels.py` — extra-port path routers
- `frontend/.../templates/launch-modal.tsx` — easy/advanced toggle, layout B
- `frontend/.../templates/builder/**` — **new** shared builder + sections + controls
- `frontend/.../hooks/use-launch-config.ts` — extend for new fields/clone/registry
- routes for `/templates/new`, `/templates/:id/edit`
- tests under `backend/tests/` and frontend test dirs
