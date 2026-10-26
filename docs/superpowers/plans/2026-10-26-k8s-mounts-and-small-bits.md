# k8s phases 3 + 4: managed mounts (guided manual) + small bits

TDD, one semantic commit per task, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`,
no push. Gate: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`.
Keep files < 500 lines; `main.py` is 519 — net-shrink it in Task 6 (move loops out) rather than grow it.

## Phase 3 — managed mounts on k8s = guided manual (owner decision)
No pods/exec, no Deployment patching outside `styx-instances`. Ever.

### Task 1 — plan (`services/mount_jobs.py:plan_mount`)
At the top: if `Settings().ROUTE_BACKEND == "k8s"`: if preset has a `config_file` method, return
`MountPlan(method="config_file", path=<first path>, fmt=<format>, key=<key>, needs_consent=False,
reason=f"On Kubernetes, Styx can't edit {preset.name}'s files. Set `{key}` to `/{slug}` in
`{path}` and restart the app — or switch this service to cookie-root mode, which needs no base path.",
manual=True)` (add `manual: bool = False` to MountPlan). No preset method -> existing "can't be
configured" reason. Never call `docker.read_file` on k8s.
Expose `manual` wherever MountPlan is serialised (grep `MountPlan` / `service_mounts.py` response
schema) so the frontend can show the instructions.

### Task 2 — apply (`routers/service_mounts.py`)
Apply/job endpoints on k8s -> HTTP 422 "Managed mounts are manual on Kubernetes: see the plan's
instructions." `_needs_setup` must not keep a k8s service stuck: on k8s, a `docker-local` path-mode
service is NOT "needs setup" (the admin confirms by hand). Check `routers/services.py:_needs_setup`.

### Task 3 — frontend
Find where the mount plan is shown (grep `needs_consent` / `already_set` in `frontend/src`). When
`manual` is true, show the `reason` text as instructions and hide the Apply button. Gate with
`cd frontend && npm run build` (tsc -b), plus any existing frontend tests for that component.

## Phase 4 — small bits

### Task 4 — instance usage via metrics-server
- `deploy/k8s/instances.yaml` Role: add `metrics.k8s.io` `pods` get/list.
- `K8sInstanceRuntime.instance_usage(name) -> dict` -> GET
  `/apis/metrics.k8s.io/v1beta1/namespaces/{ns}/pods?labelSelector=app={name}`; return
  `{"cpu_percent", "memory_mb", "memory_limit_mb", "memory_percent"}` (cpu % of the Deployment's
  cpu limit; parse `250m`, `1`, `123456n`, `512Mi`, `1Gi`, `1048576Ki`). Missing -> zeros.
- `DockerManager.instance_usage(container_id)` = the existing math from `routers/instances.py`
  stats endpoint (move it, don't duplicate). Router + `main.py` metrics loops call `instance_usage`.

### Task 5 — diagnostics + setup preflight
- `services/diagnostics.py`: on k8s the first check is key `"kubernetes"` (ok if `GET /version`
  via `incluster_client().get_json("/version")` works, detail = gitVersion) instead of `"docker"`.
  `_check_traefik_routes` on k8s: ok if `list_names(traefik IngressRoute, K8S_NAMESPACE, managed
  selector)` returns ≥1 (detail = count). GPU on k8s: detail `"amd.com/gpu via device plugin"` ok.
  Frontend: if the Health page maps check keys to labels, add `kubernetes`.
- `routers/auth.py` setup_preflight: on k8s report the same k8s API check instead of docker ping
  (keep the response field names; check what the frontend reads).

### Task 6 — images, icons, screenshots, main.py size
- `routers/images.py`: use `instance_runtime()`; on k8s remove/purge only drop DB rows
  (runtime `remove_image` is already a no-op). Test.
- `routers/service_icons.py`: already goes through `get_docker_manager` -> fine; add one k8s test
  that refresh_icon uses the httpx path.
- Screenshots on k8s: leave disabled (loop returns early) — confirm instance cards fall back
  cleanly (API returns 404/empty, not 500). Test.
- Move the background loops out of `main.py` into `app/services/background_loops.py` so main.py
  < 500 lines. Pure move, no behaviour change.

Report: commits, counts, deviations.
