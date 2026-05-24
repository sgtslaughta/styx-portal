import yaml
from pathlib import Path

from app.config import Settings

_settings = Settings()


def write_routes(instances: list[dict], domain: str | None = None):
    """Write Traefik dynamic config with routes for all services + running instances."""
    domain = domain or _settings.DOMAIN
    out_dir = Path(_settings.TRAEFIK_DYNAMIC_DIR)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return

    middlewares: dict = {}
    config: dict = {
        "http": {
            "routers": {
                "frontend": {
                    "rule": f"Host(`{domain}`)",
                    "entryPoints": ["web"],
                    "service": "frontend",
                    "priority": 1,
                },
                "api": {
                    "rule": f"Host(`{domain}`) && PathPrefix(`/api`)",
                    "entryPoints": ["web"],
                    "service": "api",
                    "priority": 100,
                },
                "dashboard": {
                    "rule": f"Host(`traefik.{domain}`)",
                    "entryPoints": ["web"],
                    "service": "api@internal",
                },
            },
            "services": {
                "frontend": {
                    "loadBalancer": {"servers": [{"url": "http://frontend:3000"}]}
                },
                "api": {
                    "loadBalancer": {"servers": [{"url": "http://backend:8000"}]}
                },
            },
        }
    }

    has_https = False
    for inst in instances:
        inst_id = inst["id"]
        subdomain = inst["subdomain"]
        port = inst.get("port", 3001)
        protocol = inst.get("protocol", "https")
        container_name = f"selkies-{subdomain}"

        strip_mw = f"strip-{subdomain}"
        middlewares[strip_mw] = {
            "stripPrefix": {"prefixes": [f"/i/{subdomain}"]}
        }

        config["http"]["routers"][inst_id] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/i/{subdomain}`)",
            "entryPoints": ["web"],
            "middlewares": [strip_mw],
            "service": inst_id,
            "priority": 50,
        }
        svc_config: dict = {
            "servers": [{"url": f"{protocol}://{container_name}:{port}"}],
        }
        if protocol == "https":
            svc_config["serversTransport"] = "selkies-transport"
            has_https = True
        config["http"]["services"][inst_id] = {"loadBalancer": svc_config}

    if middlewares:
        config["http"]["middlewares"] = middlewares
    if has_https:
        config["http"]["serversTransports"] = {
            "selkies-transport": {"insecureSkipVerify": True}
        }

    out_file = out_dir / "routes.yml"
    out_file.write_text(yaml.dump(config, default_flow_style=False))
