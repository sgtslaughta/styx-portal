import pytest
from pydantic import ValidationError

from app.schemas import TemplateCreate
from app.services.route_writer import build_routes_config
from app.services.template_validation import resolve_volume_name


@pytest.mark.parametrize("name", [
    "traefik-dynamic", "styx_db-data", "/etc", "../x", "a b", "{instance_id}/../x", "x" * 200,
])
def test_volume_names_rejected(name):
    with pytest.raises(ValidationError):
        TemplateCreate(name="t", display_name="t", image="x", volumes=[{"name": name, "mount": "/c"}])


@pytest.mark.parametrize("mount", ["/", "rel", "/a/../b", "/a:/b"])
def test_volume_mount_rejected(mount):
    with pytest.raises(ValidationError):
        TemplateCreate(name="t", display_name="t", image="x",
                       volumes=[{"name": "{instance_id}-h", "mount": mount}])


def test_volume_ok_and_resolve():
    TemplateCreate(name="t", display_name="t", image="x",
                   volumes=[{"name": "{instance_id}-home", "mount": "/config"}])
    assert resolve_volume_name("{instance_id}-home", "abc") == "abc-home"
    with pytest.raises(ValueError):
        resolve_volume_name("db-data", "abc")


@pytest.mark.parametrize("ep", [
    {"slug": "a`) || PathPrefix(`/", "container_port": 80},
    {"slug": "ok", "container_port": "80@evil:1"},
    {"slug": "ok", "container_port": 70000},
])
def test_extra_ports_rejected(ep):
    with pytest.raises(ValidationError):
        TemplateCreate(name="t", display_name="t", image="x", extra_ports=[ep])


def test_protocol_and_port_rejected():
    with pytest.raises(ValidationError):
        TemplateCreate(name="t", display_name="t", image="x", internal_protocol="http://evil/")
    with pytest.raises(ValidationError):
        TemplateCreate(name="t", display_name="t", image="x", internal_port=0)


def test_route_writer_skips_invalid_rows():
    inst = {"id": "i1", "subdomain": "s", "port": 80, "protocol": "http://evil/#",
            "extra_ports": []}
    cfg = build_routes_config([inst], domain="x.test")
    assert "i1" not in cfg["http"]["routers"]
    inst = {"id": "i2", "subdomain": "s", "port": 80, "protocol": "http",
            "extra_ports": [{"slug": "a`)", "container_port": 1}]}
    cfg = build_routes_config([inst], domain="x.test")
    assert "i2" in cfg["http"]["routers"] and not any("-p-" in k for k in cfg["http"]["routers"])
