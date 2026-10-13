import tarfile
from unittest.mock import MagicMock

from app.models import ProxiedService, ServicePreset
from app.services.mount_jobs import plan_mount

SUB = {"methods": [{"type": "config_file", "paths": ["/config/config/network.xml", "/config/network.xml"],
                    "format": "xml", "key": "/NetworkConfiguration/BaseUrl"}],
       "restart": True, "verify_path": "/{slug}/health"}


def _svc(**kw):
    return ProxiedService(slug="jellyfin", name="Jellyfin", kind="docker-local",
                          container="jellyfin", container_port=8096, **kw)


def _docker(files: dict, labels=None):
    d = MagicMock()
    d.read_file.side_effect = lambda c, p: (files[p] if isinstance(files[p], bytes) else files[p].encode(),
                                            tarfile.TarInfo("f")) if p in files else None
    d.container_labels.return_value = labels or {}
    return d


def _preset():
    return ServicePreset(id="jellyfin", name="J", subpath=SUB)


def test_second_path_used_when_first_missing():
    p = plan_mount(_svc(), _preset(),
                   _docker({"/config/network.xml": "<NetworkConfiguration><BaseUrl/></NetworkConfiguration>"}))
    assert p.method == "config_file" and p.path == "/config/network.xml"
    assert p.changes == [{"target": "/config/network.xml", "key": "/NetworkConfiguration/BaseUrl",
                          "old": "", "new": "/jellyfin"}]
    assert p.needs_consent is True


def test_styx_managed_label_skips_consent():
    p = plan_mount(_svc(), _preset(),
                   _docker({"/config/network.xml": "<NetworkConfiguration/>"}, {"styx.managed": "true"}))
    assert p.needs_consent is False


def test_already_set_gives_no_changes():
    p = plan_mount(_svc(), _preset(),
                   _docker({"/config/network.xml": "<NetworkConfiguration><BaseUrl>/jellyfin</BaseUrl></NetworkConfiguration>"}))
    assert p.method == "config_file" and p.changes == [] and "already" in p.reason


def test_no_file_found_is_manual():
    p = plan_mount(_svc(), _preset(), _docker({}))
    assert p.method is None and "can't find" in p.reason and "tmpfs" in p.reason


def test_url_kind_or_no_subpath_is_manual():
    assert plan_mount(ProxiedService(slug="x", name="X", kind="url"), None, MagicMock()).method is None
    assert plan_mount(_svc(), ServicePreset(id="x", name="X"), MagicMock()).method is None


def test_env_only_preset_is_manual():
    sub = {"methods": [{"type": "env", "var": "ROUTER_BASE_PATH"}]}
    assert plan_mount(_svc(), ServicePreset(id="abs", name="A", subpath=sub), _docker({})).method is None


def test_garbage_file_is_manual_not_raise():
    for blob in (b"\xff\xfe\x00not utf8\x80", b"<<<not xml"):
        p = plan_mount(_svc(), _preset(), _docker({"/config/network.xml": blob}))
        assert p.method is None and p.changes == []
        assert "couldn't read J's settings file" in p.reason
