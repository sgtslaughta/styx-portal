"""Managed base path: plan + apply job (spec §3.1, §3.2)."""
from dataclasses import dataclass, field

from app.models import ProxiedService, ServicePreset
from app.services.mount_edit import read_config


@dataclass
class MountPlan:
    method: str | None = None
    path: str | None = None
    fmt: str | None = None
    key: str | None = None
    changes: list[dict] = field(default_factory=list)
    needs_consent: bool = True
    reason: str | None = None


def plan_mount(svc: ProxiedService, preset: ServicePreset | None, docker) -> MountPlan:
    if svc.kind != "docker-local" or not svc.container:
        return MountPlan(reason="Styx can only configure apps running as local containers.")
    methods = [m for m in ((preset.subpath or {}).get("methods", []) if preset else [])
               if m.get("type") == "config_file"]   # ponytail: env method not implemented (spec §3.1)
    if not methods:
        return MountPlan(reason="This app can't be configured by Styx. Set its base path by hand.")
    needs_consent = docker.container_labels(svc.container).get("styx.managed") != "true"
    new = f"/{svc.slug}"
    for m in methods:
        for path in m["paths"]:
            got = docker.read_file(svc.container, path)
            if got is None:
                continue
            try:
                old = read_config(got[0].decode("utf-8"), m["format"], m["key"])
            except ValueError as err:  # UnicodeDecodeError is a ValueError
                return MountPlan(needs_consent=needs_consent,
                                 reason=f"Styx couldn't read {preset.name}'s settings file: {err}")
            plan = MountPlan("config_file", path, m["format"], m["key"], [], needs_consent)
            if old == new:
                plan.reason = f"Base path is already {new}."
            else:
                plan.changes = [{"target": path, "key": m["key"], "old": old, "new": new}]
            return plan
    return MountPlan(needs_consent=needs_consent,
                     reason=f"Styx can't find {preset.name}'s settings file in the container.")
