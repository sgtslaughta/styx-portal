# Metadata only: routing comes from the file provider (route_writer), never docker labels.
def generate_traefik_labels(
    instance_id: str,
    subdomain: str,
    domain: str,
    port: int,
    template_name: str,
) -> dict[str, str]:
    return {
        "styx-portal.managed": "true",
        "styx-portal.instance-id": instance_id,
        "styx-portal.template": template_name,
    }
