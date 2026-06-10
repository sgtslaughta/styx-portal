import pytest
from pydantic import ValidationError

from app.schemas import InstanceCreate


def _make(sub):
    return InstanceCreate(template_id="t", name="n", subdomain=sub)


@pytest.mark.parametrize("good", ["abc", "a", "my-desktop-2", "x" * 63])
def test_valid_subdomains(good):
    assert _make(good).subdomain == good


@pytest.mark.parametrize("bad", [
    "", "-abc", "abc-", "ab_c", "AB", "a.b", "a/b", "a`b", "a b",
    "x" * 64, "$(rm -rf)", "api", "traefik", "www",
])
def test_invalid_subdomains_rejected(bad):
    with pytest.raises(ValidationError):
        _make(bad)
