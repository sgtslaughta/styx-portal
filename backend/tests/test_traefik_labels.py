from app.services.traefik_labels import generate_traefik_labels


def test_labels_are_metadata_only():
    labels = generate_traefik_labels(
        instance_id="abc123", subdomain="dev", domain="example.com", port=3001,
        template_name="dev-desktop")
    assert labels == {"styx-portal.managed": "true", "styx-portal.instance-id": "abc123",
                      "styx-portal.template": "dev-desktop"}
    assert not any(k.startswith("traefik.") for k in labels)
