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


def test_missing_hint_appended():
    preset = ServicePreset(id="jellyfin", name="Jellyfin", subpath={**SUB, "missing_hint": "Click Save once."})
    p = plan_mount(_svc(), preset, _docker({}))
    assert p.method is None and p.reason.endswith("Click Save once.")


def test_jellyfin_preset_has_hint():
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parents[2] / "templates/services/jellyfin.json").read_text())
    assert "Save once" in data["subpath"]["missing_hint"]


def test_read_file_errors_become_a_reason_not_a_500():
    import docker.errors
    for err in (ValueError("too big"), docker.errors.APIError("boom")):
        d = _docker({})
        d.read_file.side_effect = err
        p = plan_mount(_svc(), _preset(), d)
        assert p.method is None and "couldn't read" in p.reason


TEMPLATE = ('<?xml version="1.0" encoding="utf-8"?>\n<NetworkConfiguration>\n  <BaseUrl />\n'
            '</NetworkConfiguration>\n')
CREATE = {"path": "/config/config/network.xml", "owner_from": "/config/config/system.xml",
          "template": TEMPLATE}


def _create_preset(create=CREATE):
    sub = {**SUB, "methods": [{**SUB["methods"][0], **({"create": create} if create else {})}]}
    return ServicePreset(id="jellyfin", name="Jellyfin", subpath=sub)


def test_missing_file_with_create_plans_a_new_file():
    p = plan_mount(_svc(), _create_preset(), _docker({"/config/config/system.xml": "<x/>"}))
    assert p.method == "config_file" and p.create is True and p.path == CREATE["path"]
    assert p.changes == [{"target": CREATE["path"], "key": "/NetworkConfiguration/BaseUrl",
                          "old": "", "new": "/jellyfin", "created": True}]
    assert p.reason is None


def test_missing_file_with_create_but_no_owner_keeps_reason():
    p = plan_mount(_svc(), _create_preset(), _docker({}))
    assert p.method is None and p.create is False and "can't find" in p.reason


def test_missing_file_without_create_unchanged():
    p = plan_mount(_svc(), _create_preset(None), _docker({"/config/config/system.xml": "<x/>"}))
    assert p.method is None and p.create is False


def test_owner_read_error_keeps_reason():
    d = _docker({})
    d.read_file.side_effect = lambda c, path: (_ for _ in ()).throw(ValueError("x")) \
        if path == CREATE["owner_from"] else None
    p = plan_mount(_svc(), _create_preset(), d)
    assert p.method is None and "can't find" in p.reason


def test_jellyfin_preset_creates_network_xml():
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).parents[2] / "templates/services/jellyfin.json").read_text())
    c = data["subpath"]["methods"][0]["create"]
    assert c["path"] == "/config/config/network.xml" and c["owner_from"] == "/config/config/system.xml"
    assert c["template"].endswith("<BaseUrl />\n</NetworkConfiguration>\n")
    assert c["path"] in data["subpath"]["methods"][0]["paths"]


def test_retry_only_when_settings_file_is_missing():
    assert plan_mount(_svc(), _preset(), _docker({})).retry is True
    assert plan_mount(_svc(), _create_preset(), _docker({})).retry is True
    ok = _docker({"/config/network.xml": "<NetworkConfiguration><BaseUrl/></NetworkConfiguration>"})
    assert plan_mount(_svc(), _preset(), ok).retry is False
    done = _docker({"/config/network.xml": "<NetworkConfiguration><BaseUrl>/jellyfin</BaseUrl></NetworkConfiguration>"})
    assert plan_mount(_svc(), _preset(), done).retry is False
    assert plan_mount(_svc(), _create_preset(), _docker({"/config/config/system.xml": "<x/>"})).retry is False
    assert plan_mount(_svc(), ServicePreset(id="x", name="X"), MagicMock()).retry is False
    bad = _docker({"/config/network.xml": b"\xff\xfe"})
    assert plan_mount(_svc(), _preset(), bad).retry is False
