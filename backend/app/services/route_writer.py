import base64
import logging
import yaml
from pathlib import Path

from app.config import Settings

logger = logging.getLogger("styx-portal")
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


def build_routes_config(instances: list[dict], domain: str,
                        deploy_mode: str = "tunnel",
                        workstations: list[dict] | None = None) -> dict:
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

    has_workstations = bool(workstations)
    for ws in workstations or []:
        sub = ws["subdomain"]
        strip_mw = f"strip-w-{sub}"
        auth_header_mw = f"auth-ws-{sub}"
        middlewares[strip_mw] = {"stripPrefix": {"prefixes": [f"/w/{sub}"]}}

        # Credential injection middleware (if selkies_password is available)
        if "selkies_password" in ws and ws["selkies_password"]:
            creds = base64.b64encode(
                f"styx:{ws['selkies_password']}".encode()).decode()
            middlewares[auth_header_mw] = {"headers": {"customRequestHeaders": {
                "Authorization": f"Basic {creds}"}}}

        rid = f"ws-{ws['id']}"
        router_middlewares = ["instance-unavailable-errors", "ws-forward-auth", strip_mw]
        if "selkies_password" in ws and ws["selkies_password"]:
            router_middlewares.insert(2, auth_header_mw)
        config["http"]["routers"][rid] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/w/{sub}`)",
            "middlewares": router_middlewares,
            "service": rid,
            "priority": 50,
            **_router_transport(deploy_mode, domain),
        }
        protocol = ws.get("protocol", "http")
        svc: dict = {"servers": [{"url": f"{protocol}://{ws['lan_ip']}:{ws['port']}"}]}
        if protocol == "https":
            svc["serversTransport"] = "selkies-transport"
            has_https = True
        config["http"]["services"][rid] = {"loadBalancer": svc}

    # Add shared forwardAuth middleware if any workstations exist
    if has_workstations:
        middlewares["ws-forward-auth"] = {"forwardAuth": {
            "address": "http://backend:8000/api/workstations/auth-check"}}

    config["http"]["middlewares"] = middlewares
    if has_https:
        config["http"]["serversTransports"] = {
            "selkies-transport": {"insecureSkipVerify": True}
        }
    return config


def write_routes(instances: list[dict], domain: str | None = None,
                 workstations: list[dict] | None = None):
    """Render the Traefik dynamic config to the file provider directory.

    A PermissionError here means the shared traefik-dynamic volume is not
    writable by the (non-root) backend user — log and continue rather than
    crash-looping startup; routing degrades but the portal stays up.
    """
    domain = domain or _settings.DOMAIN
    out_dir = Path(_settings.TRAEFIK_DYNAMIC_DIR)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        config = build_routes_config(instances, domain, _settings.DEPLOY_MODE, workstations)
        (out_dir / "routes.yml").write_text(yaml.dump(config, default_flow_style=False))
    except PermissionError:
        logger.error(
            "Cannot write Traefik routes to %s — volume not writable by backend "
            "user. Instance routing will not update. Fix volume ownership "
            "(chown 1000:1000) and restart.", out_dir,
        )


async def refresh_routes_from_db(session):
    """Query running/idle instances and (re)write the Traefik routes file."""
    from sqlmodel import select
    from app.models import Instance, ServiceTemplate, Workstation
    from app.security.crypto import decrypt_secret

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
    ws_result = await session.exec(
        select(Workstation).where(Workstation.status == "online"))
    ws_data = []
    for w in ws_result.all():
        ws_dict = {
            "id": w.id, "subdomain": w.subdomain, "lan_ip": w.lan_ip,
            "port": w.port, "protocol": w.protocol,
        }
        # Include decrypted password if available
        if w.selkies_password_enc:
            ws_dict["selkies_password"] = decrypt_secret(w.selkies_password_enc)
        ws_data.append(ws_dict)
    write_routes(data, workstations=ws_data)
