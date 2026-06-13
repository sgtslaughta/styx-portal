from app.models import ServiceTemplate


def test_template_new_fields_have_safe_defaults():
    t = ServiceTemplate(name="x", display_name="X", image="img")
    assert t.shared is False
    assert t.restart_policy == "no"
    assert t.read_only_rootfs is False
    assert t.tmpfs == []
    assert t.extra_hosts == {}
    assert t.ulimits == []
    assert t.extra_ports == []
    assert t.entrypoint is None
    assert t.command is None
    assert t.devices == []
    assert t.privileged is False
    assert t.extra_docker_args == {}
