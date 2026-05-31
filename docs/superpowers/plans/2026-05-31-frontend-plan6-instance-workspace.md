# Frontend Rework — Plan 6: Instance Workspace (40/60 master-detail + recreate)

> **For agentic workers:** Backend tasks use TDD (pytest); run `cd backend && .venv/bin/python -m pytest -v`. Frontend has NO test runner — verify with `cd frontend && npm run lint` + `npm run build`. Commit per task. PRESERVE existing behavior. Branch: `frontend-rework`.

**Goal:** Replace the Instances drawer with a persistent 40/60 master-detail: left = compact instance list, right = rich editable detail (live resource graphs + read-only LinuxServer.io info + the FULL launch-wizard config editor). Saving template-level changes recreates the container **in place, reusing named volumes so data is preserved**. Name/env/session changes stay in-place. Responsive: on narrow screens the detail overlays the list.

**Decisions (locked):** narrow = list with detail overlay; full config editable via recreate-in-place reusing volumes; LSIO info = read-only section.

---

# Part A — Backend: recreate-in-place endpoint

## Task A1: Extract shared container-build helper (refactor, keep tests green)

**Files:** Modify `backend/app/routers/instances.py`

The `start_instance` endpoint (lines ~213–246) has a "recreate container from template + instance.volume_names" branch. Extract it into a module-level helper so `recreate_instance` can reuse it.

- [ ] **Step 1:** Add a helper above the routes:
```python
async def _build_and_start_container(instance, template, docker):
    """(Re)create the Docker container for an instance from its template,
    mounting the instance's existing named volumes (data preserved), then start it.
    Sets instance.container_id. Caller commits."""
    volumes = {}
    for vol, vol_name in zip(template.volumes, instance.volume_names):
        await asyncio.to_thread(docker.create_volume, vol_name)
        volumes[vol_name] = {"bind": vol["mount"], "mode": "rw"}

    env = {**template.env_vars, **(instance.env_overrides or {})}
    labels = generate_traefik_labels(
        instance_id=instance.id,
        subdomain=instance.subdomain,
        domain=_settings.DOMAIN,
        port=template.internal_port,
        template_name=template.name,
    )
    container_id = await asyncio.to_thread(
        docker.create_container,
        name=f"selkies-{instance.subdomain}",
        image=template.image,
        labels=labels,
        environment=env,
        volumes=volumes,
        port=template.internal_port,
        gpu_enabled=template.gpu_enabled,
        gpu_count=template.gpu_count,
        memory_limit=template.memory_limit,
        shm_size=template.shm_size,
    )
    instance.container_id = container_id
    await asyncio.to_thread(docker.start_container, container_id)
    return container_id
```
- [ ] **Step 2:** Replace the `else:` recreate branch body in `start_instance` (lines ~213–246, after fetching `template` and the 404/400 guard) with a call to `await _build_and_start_container(instance, template, docker)`. Keep the `template` fetch + "Template no longer exists" guard.
- [ ] **Step 3:** Run tests — confirm still green:
```bash
cd backend && .venv/bin/python -m pytest -v && .venv/bin/python -m ruff check app/
```
- [ ] **Step 4:** Commit:
```bash
git add backend/app/routers/instances.py
git commit -m "refactor(backend): extract _build_and_start_container helper"
```

## Task A2: Add recreate endpoint (TDD)

**Files:** Modify `backend/app/routers/instances.py`; Test `backend/tests/` (add to the instances test file — read the existing one first to match fixtures).

- [ ] **Step 1: Write the failing test.** Read the existing instance tests + `conftest.py` to match fixtures (in-memory DB, mocked `get_docker_manager`). Add a test that: seeds a template (with a volume def) + a running instance with `volume_names` + `container_id`; mocks docker so `get_container_status` returns running, `create_container` returns a new id; PATCHes/PUTs the template image; POSTs `/instances/{id}/recreate`; asserts 200, response `status == "running"`, a NEW `container_id`, `volume_names` unchanged in length, and that `remove_container` + `create_container` were called (old container removed, new created). Use the existing test's mocking style.
- [ ] **Step 2:** Run it — verify it fails (404/endpoint missing):
```bash
cd backend && .venv/bin/python -m pytest -v -k recreate
```
- [ ] **Step 3: Implement the endpoint** (place after `restart_instance`):
```python
@router.post("/{instance_id}/recreate", response_model=Instance)
async def recreate_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
):
    """Rebuild the instance's container from its (updated) template, reusing the
    instance's named volumes so persistent data is preserved. Same instance id/subdomain."""
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    template = await session.get(ServiceTemplate, instance.template_id)
    if not template:
        raise HTTPException(400, "Template no longer exists, cannot recreate")

    # Remove the old container, keep volumes.
    if instance.container_id:
        status = await asyncio.to_thread(docker.get_container_status, instance.container_id)
        if status["status"] != "not_found":
            if status["status"] not in ("exited",):
                await asyncio.to_thread(docker.stop_container, instance.container_id)
            await asyncio.to_thread(docker.remove_container, instance.container_id)

    # Recompute volume names from the (possibly updated) template. instance.id is stable,
    # so unchanged volume defs yield identical names -> create_volume returns the existing
    # volume -> data preserved. New defs create new volumes; removed defs are left orphaned.
    instance.volume_names = [
        vol["name"].replace("{instance_id}", instance.id) for vol in template.volumes
    ]

    await _build_and_start_container(instance, template, docker)

    now = datetime.now(timezone.utc)
    instance.status = "running"
    instance.started_at = now
    instance.last_activity = now
    instance.error_message = None
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="recreated")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    await _refresh_routes(session)
    return instance
```
- [ ] **Step 4:** Run tests — verify pass + lint:
```bash
cd backend && .venv/bin/python -m pytest -v && .venv/bin/python -m ruff check app/
```
- [ ] **Step 5:** Commit:
```bash
git add backend/app/routers/instances.py backend/tests/
git commit -m "feat(backend): recreate-in-place endpoint reusing named volumes (data preserved)"
```

---

# Part B — Frontend: API + reusable wizard form

## Task B1: API client + hook for recreate

**Files:** Modify `frontend/src/api/client.ts`, `frontend/src/hooks/use-instances.ts`

- [ ] **Step 1:** In `client.ts`, after `restartInstance`, add:
```ts
  recreateInstance: (id: string) =>
    request<Instance>(`/instances/${id}/recreate`, { method: "POST" }),
```
- [ ] **Step 2:** In `use-instances.ts`, add a hook mirroring `useRestartInstance`:
```ts
export function useRecreateInstance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.recreateInstance(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}
```
- [ ] **Step 3:** Verify `npm run lint`. Commit:
```bash
git add src/api/client.ts src/hooks/use-instances.ts
git commit -m "feat(frontend): recreateInstance api + hook"
```

## Task B2: Extract `useLaunchConfig` hook from launch-modal

**Files:** Create `frontend/src/hooks/use-launch-config.ts`; Modify `frontend/src/components/templates/launch-modal.tsx`

Goal: move ALL the launch form state + prefill + `buildTemplateData` out of launch-modal into a reusable hook that can initialize from a registry image, a template, OR an existing template+instance.

- [ ] **Step 1:** Create `use-launch-config.ts` exporting:
```ts
export interface LaunchConfig {
  name: string; setName: (v: string) => void;
  subdomain: string; setSubdomain: (v: string) => void;
  image: string; setImage: (v: string) => void;
  icon: string; setIcon: (v: string) => void;
  memoryLimit: string; setMemoryLimit: (v: string) => void;
  cpuLimit: string; setCpuLimit: (v: string) => void;
  shmSize: string; setShmSize: (v: string) => void;
  envVars: Record<string, string>; setEnvVars: (v: Record<string, string>) => void;
  envDescriptions: Record<string, string>;
  gpuEnabled: boolean; setGpuEnabled: (v: boolean) => void;
  gpuDevices: string[]; setGpuDevices: (v: string[]) => void;
  volumes: VolumeEntry[]; setVolumes: (v: VolumeEntry[]) => void;
  ports: PortEntry[]; setPorts: (v: PortEntry[]) => void;
  securityOpts: SecurityOpt[]; setSecurityOpts: (v: SecurityOpt[]) => void;
  customOpts: CustomOpt[]; setCustomOpts: (v: CustomOpt[]) => void;
  idleTimeout: string; setIdleTimeout: (v: string) => void;
  gracePeriod: string; setGracePeriod: (v: string) => void;
  buildTemplateData: () => ReturnType<typeof buildData>;
}
export function useLaunchConfig(opts: {
  registryImage?: RegistryImage | null;
  template?: ServiceTemplate | null;
  instance?: Instance | null;
}): LaunchConfig
```
Move the prefill consts (current launch-modal lines ~39–106), all `useState` (lines ~93–108), `isSelkiesImage`/`detectPortAndProtocol`/`buildTemplateData` (lines ~110–148), and the `VolumeEntry/PortEntry/SecurityOpt/CustomOpt` interfaces (lines ~28–31) into this hook/module. When `opts.instance` is provided, override the prefill with: `name = instance.name`, `subdomain = instance.subdomain`, `envVars = { ...template.env_vars, ...instance.env_overrides }`, and session timeouts from `instance.session_config`. Export the interfaces too.
- [ ] **Step 2:** In launch-modal, replace the removed state/logic with `const cfg = useLaunchConfig({ registryImage, template });` and reference `cfg.name`, `cfg.setName`, etc. (Tasks B3/B4 finish the JSX wiring; this step just compiles.)
- [ ] **Step 3:** Verify `npm run lint`. Commit:
```bash
git add src/hooks/use-launch-config.ts src/components/templates/launch-modal.tsx
git commit -m "refactor(templates): extract useLaunchConfig hook"
```

## Task B3: Extract `LaunchConfigFields` presentational component

**Files:** Create `frontend/src/components/templates/launch-config-fields.tsx`; Modify `launch-modal.tsx`

- [ ] **Step 1:** Create `launch-config-fields.tsx` exporting `LaunchConfigFields({ cfg, gpuInfo }: { cfg: LaunchConfig; gpuInfo: GpuInfo | undefined })`. Move the core fields block (name/subdomain/image/icon — launch-modal lines ~199–208), the `<GpuIndicator .../>` usage, and the `<Tabs>` config block (Resources/Env/Volumes/Ports/Security/Selkies — lines ~218–323) into it, reading/writing through `cfg.*`. Import `GpuIndicator`, `SelkiesSettings`, `EnvEditor`, ui primitives as needed.
- [ ] **Step 2:** In launch-modal, render `<LaunchConfigFields cfg={cfg} gpuInfo={gpuInfo} />` between the header and the changelog/setup/footer. launch-modal keeps: dialog wrapper, header (icon/title/description), `upsertTemplate`/`handleSaveAndLaunch`/`handleSaveTemplate`, changelog/setup links, footer buttons.
- [ ] **Step 3:** Verify `npm run lint` and that launch-modal is now < 180 lines. Commit:
```bash
git add src/components/templates/launch-config-fields.tsx src/components/templates/launch-modal.tsx
git commit -m "refactor(templates): extract LaunchConfigFields, launch-modal consumes shared form"
```

## Task B4: Manual-verify launch flow unchanged

- [ ] **Step 1:** `npm run build`. Manual smoke: open registry → import → all 6 tabs + GPU indicator render and edit; Save & Launch + Save as Template both still work. Confirm no behavior change. (No commit unless a fix is needed.)

---

# Part C — Frontend: registry lookup

## Task C1: `useRegistryImage` hook + image→name helper

**Files:** Modify `frontend/src/hooks/use-registry.ts`; Create/extend `frontend/src/lib/utils.ts` (add helper)

- [ ] **Step 1:** Add to `utils.ts`:
```ts
/** Extract the LinuxServer image short-name from a docker image ref, or null.
 * e.g. "lscr.io/linuxserver/firefox:latest" -> "firefox". Non-LSIO images -> null. */
export function linuxserverImageName(image: string): string | null {
  const m = image.match(/(?:lscr\.io\/)?linuxserver\/([^:@/]+)/i);
  return m ? m[1]! : null;
}
```
- [ ] **Step 2:** In `use-registry.ts`, add (mirror the existing query style):
```ts
export function useRegistryImage(name: string | null) {
  return useQuery({
    queryKey: ["registry-image", name],
    queryFn: () => api.getRegistryImage(name!),
    enabled: !!name,
    staleTime: 1000 * 60 * 60,
    retry: false,
  });
}
```
- [ ] **Step 3:** Verify `npm run lint`. Commit:
```bash
git add src/hooks/use-registry.ts src/lib/utils.ts
git commit -m "feat(frontend): useRegistryImage hook + linuxserverImageName helper"
```

---

# Part D — Frontend: detail pane + workspace layout

## Task D1: Registry info section component

**Files:** Create `frontend/src/components/instances/registry-info.tsx`

- [ ] **Step 1:** Create `RegistryInfo({ image }: { image: RegistryImage })` — a read-only section: logo + name + version, stars/pulls, category badge, description, GitHub/project/setup links (open in new tab), and a collapsible changelog (`<details>`) and env-var docs list (name + desc from `image.config?.env_vars`). Use tokens only; compact. Render nothing if `image` is null (caller guards).
- [ ] **Step 2:** Verify `npm run lint`. Commit:
```bash
git add src/components/instances/registry-info.tsx
git commit -m "feat(instances): read-only LinuxServer.io registry info section"
```

## Task D2: InstanceDetailPane (inline, replaces the drawer)

**Files:** Create `frontend/src/components/instances/instance-detail-pane.tsx`; (the old `instance-detail.tsx` + `detail-tabs.tsx` will be removed in D4)

- [ ] **Step 1:** Create `InstanceDetailPane({ instanceId }: { instanceId: string | null })`. Behavior:
  - If `instanceId` is null → render a centered placeholder ("Select an instance to view details").
  - Resolve the instance from `useInstances()` by id, and its template from `useTemplates()`. If the instance vanished (destroyed), render the placeholder.
  - **Header:** name, `<StatusBadge status showIcon />`, `<ActionBar instance />` (no `showConnect` change — default).
  - **Resources:** when running, `useInstanceStats(id, true)` → two `<Gauge>` (CPU `var(--chart-1)`, RAM `var(--chart-2)`) + the `<OverlaySparkline>` (CHART_COLORS) + uptime/idle via `formatDuration` (compute like instance-card).
  - **Registry info:** `const lsName = template ? linuxserverImageName(template.image) : null; const { data: regImg } = useRegistryImage(lsName);` → if `regImg`, render `<RegistryInfo image={regImg} />`.
  - **Config editor:** `const cfg = useLaunchConfig({ template, instance });` then `<LaunchConfigFields cfg={cfg} gpuInfo={gpuInfo} />` (gpuInfo from `useGpuInfo()`). Re-init the cfg when `instanceId` changes (the hook keys off opts; if it doesn't reset on instance change, give the pane a `key={instanceId}` at the call site in D3 so it remounts — DO THIS in D3).
  - **Save logic:** compute diffs vs the instance/template:
    - `inPlaceChanged` = name changed OR env (cfg.envVars vs `{...template.env_vars, ...instance.env_overrides}`) changed OR session (idle/grace) changed.
    - `templateChanged` = image/icon/memory/cpu/shm/volumes/ports/security/custom/gpu changed (compare cfg.buildTemplateData() template-level fields vs current template).
    - Render a Save button (enabled when dirty). On save:
      - If `templateChanged`: open a `ConfirmDialog` (variant destructive, confirmPhrase = instance.name) titled "Rebuild & apply?" describing: "Updates the template and rebuilds the container with the new settings. The session restarts briefly. Persistent named volumes are kept — data is preserved." On confirm → `await updateTemplate.mutateAsync({ id: template.id, data: cfg.buildTemplateData() })` then `await recreate.mutateAsync(instance.id)`; toast success/error.
      - Else if `inPlaceChanged`: reuse the existing in-place logic from the old instance-detail (`useUpdateInstance`; if running and name/env changed, stop→update→start; else update). Port that logic here. toast.
  - Keep `useUpdateInstance`, `useStartInstance`, `useStopInstance`, `useRecreateInstance`, `useUpdateTemplate` as needed.
  - Track `dirty` by comparing cfg values to initial (simplest: a `dirty` flag set on any field change is hard with the hook; instead derive `inPlaceChanged || templateChanged` each render and enable Save when true).
- [ ] **Step 2:** Verify `npm run lint`. Commit:
```bash
git add src/components/instances/instance-detail-pane.tsx
git commit -m "feat(instances): InstanceDetailPane — resources + LSIO info + full editor + recreate save"
```

## Task D3: InstanceWorkspace 40/60 layout + responsive; list selection highlight

**Files:** Create `frontend/src/components/instances/instance-workspace.tsx`; Modify `frontend/src/components/instances/instance-grid.tsx` (add optional `selectedId` highlight + force-compact option)

- [ ] **Step 1:** In `instance-grid.tsx`, add optional props `selectedId?: string` and `dense?: boolean`. When `selectedId` matches an item, add a highlight ring on its `SelectableWrapper` (reuse the existing `ring-2 ring-primary/60` style). When `dense` is true, default the view to `compact` and you may hide the view-cycle button (keep search/sort/filter/select). Do NOT break existing usage (props optional).
- [ ] **Step 2:** Create `InstanceWorkspace`:
```tsx
export function InstanceWorkspace() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // wide: side-by-side 40/60; narrow: list full-width, detail overlays when selectedId set
  return (
    <div className="relative flex h-[calc(100vh-8.5rem)] gap-3">
      <div className="w-full overflow-y-auto md:w-2/5 md:min-w-[320px]">
        <InstanceGrid dense selectedId={selectedId ?? undefined}
          onSelect={(i) => setSelectedId(i.id)} onLaunch={() => {/* parent handles tab switch; see D4 */}} />
      </div>
      {/* detail: inline on md+, overlay on narrow */}
      <div className={cn(
        "overflow-y-auto rounded-lg border border-border bg-card md:block md:w-3/5",
        selectedId ? "fixed inset-0 z-40 m-2 md:static md:m-0" : "hidden md:block"
      )}>
        {/* narrow back button */}
        {selectedId && (
          <button className="m-2 text-sm text-muted-foreground md:hidden" onClick={() => setSelectedId(null)}>← Back</button>
        )}
        <InstanceDetailPane key={selectedId} instanceId={selectedId} />
      </div>
    </div>
  );
}
```
Adjust the `onLaunch` wiring: `InstanceWorkspace` should accept an `onLaunch` prop and pass it through to InstanceGrid (App provides it). Add `onLaunch: () => void` to props.
- [ ] **Step 3:** Verify `npm run lint`. Commit:
```bash
git add src/components/instances/instance-workspace.tsx src/components/instances/instance-grid.tsx
git commit -m "feat(instances): InstanceWorkspace 40/60 master-detail + list selection highlight"
```

## Task D4: Wire into App, remove the old drawer

**Files:** Modify `frontend/src/App.tsx`; Delete `frontend/src/components/instances/instance-detail.tsx` and `frontend/src/components/instances/detail-tabs.tsx`

- [ ] **Step 1:** In App.tsx, replace the instances tab content (`<InstanceGrid onSelect={setSelectedInstance} onLaunch={...} />`) with `<InstanceWorkspace onLaunch={() => setActiveTab("templates")} />`. Remove the `selectedInstance` state and the `<InstanceDetail ... />` render at the bottom. Keep LaunchModal + tabs.
- [ ] **Step 2:** Delete `instance-detail.tsx` and `detail-tabs.tsx` (their roles are now in InstanceDetailPane). Remove any imports of them.
- [ ] **Step 3:** Verify `npm run lint` + `npm run build`. Commit:
```bash
git add -A src/App.tsx src/components/instances/
git commit -m "feat(instances): use InstanceWorkspace, remove old detail drawer"
```

---

## Phase Verification

- [ ] **Backend:** `cd backend && .venv/bin/python -m pytest -v && .venv/bin/python -m ruff check app/` — all green.
- [ ] **Frontend:** `cd frontend && npm run build` — passes. `grep -rnE "confirm\(|bg-(green|amber|red)-[0-9]|#[0-9a-fA-F]{6}" src/` — no native confirm/hardcoded status colors/hex (sparkline/charts use CHART tokens; name-scrim rgba in icon-viewport allowed).
- [ ] **Manual smoke:** Instances tab → 40/60 split; select an instance → detail shows status+ActionBar, live CPU/RAM gauges, LSIO info (for a linuxserver image), and the full config editor. Edit a name/env → Save = in-place (no rebuild). Edit memory/image/volume → Save → confirm dialog → template updates + container recreates, instance stays, data on volumes preserved (verify a volume file survives if testable). Narrow window → list full width, selecting overlays detail with Back. Both themes.

## Notes for executor
- Reuse the in-place save logic from the OLD `instance-detail.tsx` (read it before deleting) for the name/env/session PATCH + stop→update→start path.
- Do NOT change other hooks or the API client beyond the additions specified.
- If `useLaunchConfig` doesn't re-init when switching instances, rely on the `key={selectedId}` remount in InstanceWorkspace (already specified) — do not add fragile effects.
- The shared `LaunchConfigFields` must render identically in the wizard and the detail editor — that is the whole point of the extraction.
