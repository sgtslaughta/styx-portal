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

    config: dict = {
        "http": {
            "middlewares": {
                "authentik": {
                    "forwardAuth": {
                        "address": f"http://{_settings.AUTHENTIK_MIDDLEWARE.split('@')[0]}/outpost.goauthentication.com/auth/traefik",
                        "trustForwardHeader": True,
                        "authResponseHeaders": [
                            "X-Authentik-Username",
                            "X-Authentik-Groups",
                            "X-Authentik-Email",
                            "X-Authentik-Name",
                            "X-Authentik-Uid",
                        ],
                    }
                }
            },
            "routers": {
                "frontend": {
                    "rule": f"Host(`{domain}`)",
                    "entryPoints": ["web"],
                    "middlewares": ["authentik"],
                    "service": "frontend",
                },
                "api": {
                    "rule": f"Host(`api.{domain}`)",
                    "entryPoints": ["web"],
                    "middlewares": ["authentik"],
                    "service": "api",
                },
                "dashboard": {
                    "rule": f"Host(`traefik.{domain}`)",
                    "entryPoints": ["web"],
                    "middlewares": ["authentik"],
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

    for inst in instances:
        inst_id = inst["id"]
        subdomain = inst["subdomain"]
        port = inst.get("port", 3001)
        container_name = f"selkies-{subdomain}"

        config["http"]["routers"][inst_id] = {
            "rule": f"Host(`{subdomain}.{domain}`)",
            "entryPoints": ["web"],
            "middlewares": ["authentik"],
            "service": inst_id,
        }
        config["http"]["services"][inst_id] = {
            "loadBalancer": {"servers": [{"url": f"http://{container_name}:{port}"}]}
        }

    out_file = out_dir / "routes.yml"
    out_file.write_text(yaml.dump(config, default_flow_style=False))
