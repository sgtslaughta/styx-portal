from app.schemas import TemplateCreate


def test_create_schema_accepts_new_fields():
    body = TemplateCreate(
        name="t", display_name="T", image="img",
        restart_policy="always", read_only_rootfs=True, tmpfs=["/tmp"],
        extra_hosts={"a": "1.2.3.4"},
        ulimits=[{"name": "nofile", "soft": 1, "hard": 2}],
        extra_ports=[{"container_port": 8080, "label": "code", "slug": "code", "strip_prefix": True}],
        entrypoint=["/bin/sh"], command=["-c", "x"], devices=["/dev/dri:/dev/dri"],
        privileged=True, extra_docker_args={"hostname": "h"}, shared=True,
    )
    assert body.restart_policy == "always"
    assert body.extra_ports[0]["slug"] == "code"
    assert body.shared is True


def test_create_schema_defaults():
    body = TemplateCreate(name="t", display_name="T", image="img")
    assert body.shared is False
    assert body.restart_policy == "no"
    assert body.tmpfs == []
    assert body.extra_docker_args == {}
