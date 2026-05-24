def generate_traefik_labels(
    instance_id: str,
    subdomain: str,
    domain: str,
    port: int,
    template_name: str,
    auth_middleware: str | None = None,
) -> dict[str, str]:
    labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{instance_id}.rule": f"Host(`{subdomain}.{domain}`)",
        f"traefik.http.routers.{instance_id}.entrypoints": "websecure",
        f"traefik.http.services.{instance_id}.loadbalancer.server.port": str(port),
        "selkies-hub.managed": "true",
        "selkies-hub.instance-id": instance_id,
        "selkies-hub.template": template_name,
    }
    if auth_middleware:
        labels[f"traefik.http.routers.{instance_id}.middlewares"] = auth_middleware

    return labels
