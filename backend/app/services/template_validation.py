"""Validation for template fields that reach Docker volumes and Traefik config."""
import re

VOLUME_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
SLUG_RE = re.compile(r"[a-z0-9-]{1,32}")
PROTOCOLS = {"http", "https"}


def resolve_volume_name(template_name: str, instance_id: str) -> str:
    """Instance volume name. Must be a plain name scoped to this instance."""
    if "{instance_id}" not in template_name:
        raise ValueError("volume name must contain {instance_id}")
    name = template_name.replace("{instance_id}", instance_id)
    if not VOLUME_NAME_RE.fullmatch(name) or instance_id not in name:
        raise ValueError("invalid volume name")
    return name


def validate_volumes(volumes: list[dict]) -> list[dict]:
    for v in volumes:
        if not isinstance(v, dict) or set(v) - {"name", "mount"}:
            raise ValueError("volume must be {name, mount}")
        # shape check with a dummy id; the real id is substituted at launch
        resolve_volume_name(str(v.get("name", "")), "0" * 36)
        m = str(v.get("mount", ""))
        if not m.startswith("/") or m == "/" or ".." in m.split("/") or "," in m or ":" in m:
            raise ValueError("mount must be an absolute path other than /")
    return volumes


def valid_extra_port(ep) -> bool:
    if not isinstance(ep, dict):
        return False
    cp = ep.get("container_port")
    return (
        isinstance(cp, int) and not isinstance(cp, bool) and 1 <= cp <= 65535
        and isinstance(ep.get("slug"), str) and SLUG_RE.fullmatch(ep["slug"]) is not None
        and isinstance(ep.get("strip_prefix", True), bool)
    )


def validate_extra_ports(ports: list[dict]) -> list[dict]:
    for ep in ports:
        if not valid_extra_port(ep):
            raise ValueError("extra_ports: slug [a-z0-9-]{1,32}, container_port 1-65535")
    return ports


def validate_protocol(p: str) -> str:
    if p not in PROTOCOLS:
        raise ValueError("internal_protocol must be http or https")
    return p
