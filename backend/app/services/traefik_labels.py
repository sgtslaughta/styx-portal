def generate_traefik_labels(
    instance_id: str,
    subdomain: str,
    domain: str,
    port: int,
    template_name: str,
    auth_middleware: str = "authentik@file",
) -> dict[str, str]:
    return {
        "traefik.enable": "true",
        f"traefik.http.routers.{instance_id}.rule": f"Host(`{subdomain}.{domain}`)",
        f"traefik.http.routers.{instance_id}.entrypoints": "web",
        f"traefik.http.routers.{instance_id}.middlewares": auth_middleware,
        f"traefik.http.services.{instance_id}.loadbalancer.server.port": str(port),
        "styx-portal.managed": "true",
        "styx-portal.instance-id": instance_id,
        "styx-portal.template": template_name,
    }
