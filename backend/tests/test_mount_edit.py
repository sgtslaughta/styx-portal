import json

import pytest

from app.services.mount_edit import edit_config, read_config

XML = "<?xml version='1.0' encoding='utf-8'?>\n<Config>\n  <Port>8989</Port>\n  <UrlBase></UrlBase>\n</Config>"


def test_xml_set_existing():
    new, old = edit_config(XML, "xml", "/Config/UrlBase", "/sonarr")
    assert old == "" and read_config(new, "xml", "/Config/UrlBase") == "/sonarr"
    assert "<Port>8989</Port>" in new


def test_xml_creates_missing_child():
    new, old = edit_config("<NetworkConfiguration/>", "xml", "/NetworkConfiguration/BaseUrl", "/jellyfin")
    assert old is None and read_config(new, "xml", "/NetworkConfiguration/BaseUrl") == "/jellyfin"


def test_xml_root_mismatch_raises():
    with pytest.raises(ValueError):
        edit_config("<Other/>", "xml", "/Config/UrlBase", "/x")


def test_xml_rejects_entities():  # no XXE / billion laughs
    with pytest.raises(ValueError):
        edit_config('<!DOCTYPE a [<!ENTITY e "x">]><Config>&e;</Config>', "xml", "/Config/UrlBase", "/x")


def test_json_dotted():
    new, old = edit_config(json.dumps({"server": {"base": "/"}}), "json", "server.base", "/abs")
    assert old == "/" and json.loads(new)["server"]["base"] == "/abs"


def test_ini_section_key():
    new, old = edit_config("[http]\nroot = /\n", "ini", "http.root", "/app")
    assert old == "/" and read_config(new, "ini", "http.root") == "/app"


def test_garbage_raises():
    with pytest.raises(ValueError):
        edit_config("{not json", "json", "a", "b")
