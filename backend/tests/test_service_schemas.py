# backend/tests/test_service_schemas.py
import pytest
from pydantic import ValidationError

from app.schemas import ProxiedServiceCreate


def _base(**kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://192.168.1.10:8989", "mount_mode": "path", "auth_mode": "sso"}
    d.update(kw)
    return d


def test_valid_url_service():
    s = ProxiedServiceCreate(**_base())
    assert s.slug == "sonarr"


@pytest.mark.parametrize("slug", ["api", "Api", "API", "_styx", "if", "outpost.goauthentik.io",
                                  ".well-known", "-", "w", "i", "has space", ""])
def test_reserved_or_invalid_slug_rejected(slug):
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(slug=slug))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "unix:///var/run/docker.sock", "192.168.1.1:80"])
def test_bad_upstream_scheme_rejected(url):
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(upstream_url=url))


def test_docker_local_requires_container_and_port():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(kind="docker-local", upstream_url=None))
    s = ProxiedServiceCreate(**_base(kind="docker-local", upstream_url=None,
                                     container="sonarr", container_port=8989))
    assert s.container_port == 8989


def test_bypass_rules_only_with_bypass_mode():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(auth_mode="sso",
                                     bypass_rules=[{"path_prefix": "/sonarr/api"}]))
    s = ProxiedServiceCreate(**_base(auth_mode="sso-with-bypass",
                                     bypass_rules=[{"path_prefix": "/", "required_header": None}]))
    assert s.bypass_rules[0].path_prefix == "/"


def test_bypass_prefix_must_start_with_slash():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(auth_mode="sso-with-bypass",
                                     bypass_rules=[{"path_prefix": "api"}]))


@pytest.mark.parametrize("slug", ["api", "i", "w", "assets", "login", "setup", "connecting",
                                  "change-password", "accept-invite", "application", "static",
                                  "media", "flows", "ws", "source"])
def test_every_reserved_segment_rejected(slug):
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(slug=slug))


def test_slug_trailing_newline_rejected():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(slug="sonarr\n"))
