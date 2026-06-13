"""Allowlist validator for the raw `extra_docker_args` escape hatch.

Allowlist, not denylist: any kwarg not explicitly allowed is rejected. Some
kwargs are forbidden for everyone (escape/auth-bypass risks); some are gated
to admins. The router decides `is_admin`; this module enforces the surface.
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
}

# Allowed only when is_admin=True.
_ADMIN_ONLY = {
    "sysctls",
    "cgroup_parent",
    "runtime",
    "device_cgroup_rules",
    "security_opt",
    "tmpfs",
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
        if key in _ADMIN_ONLY:
            if not is_admin:
                raise DockerArgError(f"'{key}' requires admin")
            continue
        if key in _SAFE:
            if key == "labels" and isinstance(value, dict):
                if any(k.startswith("traefik.") for k in value):
                    raise DockerArgError("labels cannot override traefik.* keys")
            continue
        raise DockerArgError(f"Unknown Docker arg '{key}'")
    return dict(args)
