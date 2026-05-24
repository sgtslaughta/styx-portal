from app.services.traefik_labels import generate_traefik_labels


def test_basic_labels():
    labels = generate_traefik_labels(
        instance_id="abc123",
        subdomain="dev",
        domain="example.com",
        port=3001,
        template_name="dev-desktop",
    )
    assert labels["traefik.enable"] == "true"
    assert labels["traefik.http.routers.abc123.rule"] == "Host(`dev.example.com`)"
    assert labels["traefik.http.routers.abc123.entrypoints"] == "web"
    assert labels["traefik.http.services.abc123.loadbalancer.server.port"] == "3001"
    assert labels["traefik.http.routers.abc123.middlewares"] == "authentik@file"
    assert labels["selkies-hub.managed"] == "true"
    assert labels["selkies-hub.instance-id"] == "abc123"
    assert labels["selkies-hub.template"] == "dev-desktop"


def test_labels_custom_middleware():
    labels = generate_traefik_labels(
        instance_id="xyz",
        subdomain="work",
        domain="my.site",
        port=3001,
        template_name="workstation",
        auth_middleware="custom-auth@file",
    )
    assert labels["traefik.http.routers.xyz.middlewares"] == "custom-auth@file"


def test_labels_custom_port():
    labels = generate_traefik_labels(
        instance_id="id1",
        subdomain="custom",
        domain="d.com",
        port=8080,
        template_name="custom",
    )
    assert labels["traefik.http.services.id1.loadbalancer.server.port"] == "8080"
