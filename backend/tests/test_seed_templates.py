"""Seed templates must ship the capability + seccomp profile their Selkies/s6
images need to boot and do GPU framebuffer capture. The default cap_drop=ALL +
default seccomp (Phase 1 confinement) otherwise crash-loops these desktops."""
import glob
import json
import os

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")


def _load():
    return [json.load(open(f)) for f in glob.glob(os.path.join(_TEMPLATES_DIR, "*.json"))]


def test_seed_templates_have_boot_capabilities():
    tmpls = _load()
    assert tmpls, "no seed templates found"
    for t in tmpls:
        caps = t.get("cap_add") or []
        # s6 init needs at least CHOWN + SETUID/SETGID to set up runtime dirs and
        # drop privileges to the desktop user.
        for needed in ("CHOWN", "SETUID", "SETGID"):
            assert needed in caps, f"{t['name']} missing cap {needed}"


def test_seed_templates_relax_seccomp_for_gpu_capture():
    for t in _load():
        secopt = t.get("security_opt") or []
        assert "seccomp=unconfined" in secopt, \
            f"{t['name']} needs seccomp=unconfined for pixelflux GPU capture"
