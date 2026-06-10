import yaml
from pathlib import Path

from app.config import Settings

_settings = Settings()


def _router_transport(deploy_mode: str, domain: str) -> dict:
    """Return entryPoints and TLS config dict based on deploy mode."""
    if deploy_mode == "direct":
        return {
            "entryPoints": ["websecure"],
            "tls": {
                "certResolver": "letsencrypt",
                "domains": [{"main": domain, "sans": [f"*.{domain}"]}],
            },
        }
    return {"entryPoints": ["web"]}


def build_routes_config(instances: list[dict], domain: str, deploy_mode: str = "tunnel") -> dict:
    """Build the Traefik dynamic config dict for all services + running instances.

    Always emits the static `unavailable-rewrite` / `instance-unavailable-errors`
    middlewares and the low-priority `instances_fallback` router so stopped /
    unknown `/i/` requests get redirected to the My Instances page.
    """
    middlewares: dict = {
        "unavailable-rewrite": {
            "replacePath": {"path": "/api/instance-unavailable"}
        },
        "instance-unavailable-errors": {
            "errors": {
                "status": ["500-599"],
                "service": "api",
                "query": "/api/instance-unavailable",
            }
        },
    }
    config: dict = {
        "http": {
            "routers": {
                "frontend": {
                    "rule": f"Host(`{domain}`)",
                    "service": "frontend",
                    "priority": 1,
                    **_router_transport(deploy_mode, domain),
                },
                "api": {
                    "rule": f"Host(`{domain}`) && PathPrefix(`/api`)",
                    "service": "api",
                    "priority": 100,
                    **_router_transport(deploy_mode, domain),
                },
                "instances_fallback": {
                    "rule": f"Host(`{domain}`) && PathPrefix(`/i/`)",
                    "middlewares": ["unavailable-rewrite"],
                    "service": "api",
                    "priority": 10,
                    **_router_transport(deploy_mode, domain),
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
        middlewares[strip_mw] = {"stripPrefix": {"prefixes": [f"/i/{subdomain}"]}}

        config["http"]["routers"][inst_id] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/i/{subdomain}`)",
            "middlewares": ["instance-unavailable-errors", strip_mw],
            "service": inst_id,
            "priority": 50,
            **_router_transport(deploy_mode, domain),
        }
        svc_config: dict = {
            "servers": [{"url": f"{protocol}://{container_name}:{port}"}],
        }
        if protocol == "https" and inst.get("tls_skip_verify"):
            svc_config["serversTransport"] = "selkies-transport"
            has_https = True
        config["http"]["services"][inst_id] = {"loadBalancer": svc_config}

    config["http"]["middlewares"] = middlewares
    if has_https:
        config["http"]["serversTransports"] = {
            "selkies-transport": {"insecureSkipVerify": True}
        }
    return config


def write_routes(instances: list[dict], domain: str | None = None):
    """Render the Traefik dynamic config to the file provider directory."""
    domain = domain or _settings.DOMAIN
    out_dir = Path(_settings.TRAEFIK_DYNAMIC_DIR)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return
    config = build_routes_config(instances, domain, _settings.DEPLOY_MODE)
    (out_dir / "routes.yml").write_text(yaml.dump(config, default_flow_style=False))


async def refresh_routes_from_db(session):
    """Query running/idle instances and (re)write the Traefik routes file."""
    from sqlmodel import select
    from app.models import Instance, ServiceTemplate

    result = await session.exec(
        select(Instance).where(Instance.status.in_(["running", "idle"]))
    )
    running = result.all()
    data = []
    for i in running:
        tmpl = await session.get(ServiceTemplate, i.template_id)
        data.append({
            "id": i.id,
            "subdomain": i.subdomain,
            "port": tmpl.internal_port if tmpl else 3001,
            "protocol": tmpl.internal_protocol if tmpl else "https",
            "tls_skip_verify": bool(tmpl.tls_skip_verify) if tmpl else False,
        })
    write_routes(data)
