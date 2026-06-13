"""Allowlist validator for the raw `extra_docker_args` escape hatch.

Safe-only hatch: any kwarg not explicitly allowed is rejected. Dangerous options
like sysctls, cgroup_parent, runtime, device_cgroup_rules have dedicated
template fields or are blocked by denylist at launch. The router decides
`is_admin`; this module enforces the surface (is_admin param kept for stability).
"""
from typing import Any


class DockerArgError(ValueError):
    """Raised when extra_docker_args contains a forbidden or unknown kwarg."""


# Forbidden for everyone — would bypass isolation or Traefik auth.
_FORBIDDEN = {
    "ports",          # raw host publishing — all ingress must go via Traefik
    "binds",          # host bind mounts — named volumes only
    "volumes_from",
    "privileged",     # has a dedicated gated field
    "cap_add",        # dedicated gated field
    "devices",        # dedicated gated field
    "pid_mode",
    "ipc_mode",
    "userns_mode",
    "network_mode",   # host/container networking
    "sysctls",        # blocked by denylist at launch
    "cgroup_parent",  # blocked by denylist at launch
    "runtime",        # blocked by denylist at launch
    "device_cgroup_rules",  # blocked by denylist at launch
    "security_opt",   # has a dedicated gated field
    "tmpfs",          # has a dedicated gated field
}

# Allowed for any caller who can reach the escape hatch.
_SAFE = {
    "hostname",
    "dns",
    "dns_search",
    "stop_signal",
    "stop_timeout",
    "working_dir",
    "init",
    "labels",
}


def validate_extra_args(args: dict[str, Any], *, is_admin: bool) -> dict[str, Any]:
    if not args:
        return {}
    for key, value in args.items():
        if key in _FORBIDDEN:
            raise DockerArgError(f"'{key}' is not allowed via extra Docker args")
        if key in _SAFE:
            if key == "labels" and isinstance(value, dict):
                if any(k.startswith("traefik.") for k in value):
                    raise DockerArgError("labels cannot override traefik.* keys")
            continue
        raise DockerArgError(f"Unknown Docker arg '{key}'")
    return dict(args)
