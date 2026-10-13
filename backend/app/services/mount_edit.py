"""Edit one value in an app config file (spec §3.1). Pure functions, no I/O.

Container config files are untrusted: every malformed or wrong-shape input
raises ValueError, never TypeError/AttributeError/RecursionError.
"""
import configparser
import io
import json
import xml.etree.ElementTree as ET  # building/serialising only

import defusedxml.ElementTree as DET
from defusedxml import DefusedXmlException

MAX_CONFIG_BYTES = 1024 * 1024  # 1 MiB cap on any config text

# Keep prefixes stable on rewrite (Jellyfin network.xml uses xsi/xsd).
ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
ET.register_namespace("xsd", "http://www.w3.org/2001/XMLSchema")


def _check_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("config exceeds 1 MiB")


def _xml_parts(key: str) -> list[str]:
    parts = [p for p in key.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"xml key needs /Root/Child: {key}")
    return parts


def _xml_root(text: str) -> ET.Element:
    try:
        return DET.fromstring(text, forbid_dtd=True)  # no XXE / entity expansion
    except (ET.ParseError, DefusedXmlException) as e:
        raise ValueError(f"bad xml: {e}") from e


def _ini(text: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str  # keep key case
    try:
        cp.read_string(text)
    except configparser.Error as e:
        raise ValueError(f"bad ini: {e}") from e
    return cp


def _ini_key(key: str) -> tuple[str, str]:
    sec, dot, k = key.partition(".")
    if not dot or not sec or not k:
        raise ValueError("ini key needs section.key")
    return sec, k


def _json_root(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"bad json: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("json root must be an object")
    return data


def _read_xml(text: str, key: str) -> str | None:
    parts = _xml_parts(key)
    root = _xml_root(text)
    if root.tag != parts[0]:
        raise ValueError(f"root is <{root.tag}>, expected <{parts[0]}>")
    node = root.find("/".join(parts[1:]))
    return None if node is None else (node.text or "")


def _read_json(text: str, key: str) -> str | None:
    cur: object = _json_root(text)
    for k in key.split("."):
        if not isinstance(cur, dict):
            raise ValueError(f"json path '{key}' crosses a non-object")
        if k not in cur:
            return None
        cur = cur[k]
    if cur is None:
        return None
    if isinstance(cur, (dict, list)):
        raise ValueError(f"json key '{key}' is not a scalar")
    return str(cur)


def _read_ini(text: str, key: str) -> str | None:
    cp = _ini(text)
    sec, k = _ini_key(key)
    return cp.get(sec, k, fallback=None)


def _edit_xml(text: str, key: str, value: str) -> tuple[str, str | None]:
    old = _read_xml(text, key)
    root = _xml_root(text)
    node = root
    for tag in _xml_parts(key)[1:]:
        child = node.find(tag)
        node = child if child is not None else ET.SubElement(node, tag)
    node.text = value
    decl = "<?xml version='1.0' encoding='utf-8'?>\n" if text.lstrip().startswith("<?xml") else ""
    return decl + ET.tostring(root, encoding="unicode"), old


def _edit_json(text: str, key: str, value: str) -> tuple[str, str | None]:
    old = _read_json(text, key)
    data = _json_root(text)
    cur = data
    *path, last = key.split(".")
    for k in path:
        nxt = cur.setdefault(k, {})
        if not isinstance(nxt, dict):
            raise ValueError(f"json path '{key}' crosses a non-object")
        cur = nxt
    cur[last] = value
    return json.dumps(data, indent=2) + "\n", old


def _edit_ini(text: str, key: str, value: str) -> tuple[str, str | None]:
    old = _read_ini(text, key)
    cp = _ini(text)
    sec, k = _ini_key(key)
    if not cp.has_section(sec):
        cp.add_section(sec)
    cp.set(sec, k, value)
    buf = io.StringIO()
    cp.write(buf)
    return buf.getvalue(), old


def read_config(text: str, fmt: str, key: str) -> str | None:
    _check_size(text)
    try:
        if fmt == "xml":
            return _read_xml(text, key)
        if fmt == "json":
            return _read_json(text, key)
        if fmt == "ini":
            return _read_ini(text, key)
    except RecursionError as e:
        raise ValueError("config nesting too deep") from e
    raise ValueError(f"unknown format {fmt}")


def edit_config(text: str, fmt: str, key: str, value: str) -> tuple[str, str | None]:
    _check_size(text)
    try:
        if fmt == "xml":
            return _edit_xml(text, key, value)
        if fmt == "json":
            return _edit_json(text, key, value)
        if fmt == "ini":
            return _edit_ini(text, key, value)
    except RecursionError as e:
        raise ValueError("config nesting too deep") from e
    raise ValueError(f"unknown format {fmt}")
