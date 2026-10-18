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


@pytest.mark.parametrize(
    "text, key",
    [("[1]", "a"), ('{"a": "s"}', "a.b"), ('{"a": [1]}', "a.b")],
)
def test_json_wrong_shape_raises_valueerror(text, key):
    with pytest.raises(ValueError):
        edit_config(text, "json", key, "x")
    with pytest.raises(ValueError):
        read_config(text, "json", key)


def test_ini_key_without_dot_raises():
    with pytest.raises(ValueError, match="ini key needs section.key"):
        edit_config("[http]\nroot = /\n", "ini", "root", "/x")
    with pytest.raises(ValueError, match="ini key needs section.key"):
        read_config("[http]\nroot = /\n", "ini", "root")


def test_oversized_config_raises():
    big = "x" * (1024 * 1024 + 1)
    for fmt in ("xml", "json", "ini"):
        with pytest.raises(ValueError):
            edit_config(big, fmt, "a.b" if fmt != "xml" else "/A/B", "x")
        with pytest.raises(ValueError):
            read_config(big, fmt, "a.b" if fmt != "xml" else "/A/B")


def test_xml_deep_nesting_raises_valueerror():
    deep = "<Config>" + "<a>" * 3000 + "</a>" * 3000 + "</Config>"
    with pytest.raises(ValueError):
        edit_config(deep, "xml", "/Config/UrlBase", "/x")


def test_xml_keeps_xsi_prefix():
    text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<UrlBase xsi:nil="true"></UrlBase></Config>'
    )
    new, _ = edit_config(text, "xml", "/Config/UrlBase", "/x")
    assert 'xsi:nil="true"' in new
    assert "ns0:" not in new and "ns1:" not in new
