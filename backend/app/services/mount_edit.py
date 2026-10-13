"""Edit one value in an app config file (spec §3.1). Pure functions, no I/O."""
import configparser
import io
import json
import xml.etree.ElementTree as ET  # building/serialising only

import defusedxml.ElementTree as DET
from defusedxml import DefusedXmlException


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


def _json_root(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"bad json: {e}") from e


def read_config(text: str, fmt: str, key: str) -> str | None:
    if fmt == "xml":
        parts = _xml_parts(key)
        root = _xml_root(text)
        if root.tag != parts[0]:
            raise ValueError(f"root is <{root.tag}>, expected <{parts[0]}>")
        node = root.find("/".join(parts[1:]))
        return None if node is None else (node.text or "")
    if fmt == "json":
        cur = _json_root(text)
        for k in key.split("."):
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return None if cur is None else str(cur)
    if fmt == "ini":
        cp = _ini(text)
        sec, _, k = key.partition(".")
        return cp.get(sec, k, fallback=None)
    raise ValueError(f"unknown format {fmt}")


def edit_config(text: str, fmt: str, key: str, value: str) -> tuple[str, str | None]:
    old = read_config(text, fmt, key)
    if fmt == "xml":
        parts = _xml_parts(key)
        root = _xml_root(text)
        node = root
        for tag in parts[1:]:
            child = node.find(tag)
            node = child if child is not None else ET.SubElement(node, tag)
        node.text = value
        decl = "<?xml version='1.0' encoding='utf-8'?>\n" if text.lstrip().startswith("<?xml") else ""
        return decl + ET.tostring(root, encoding="unicode"), old
    if fmt == "json":
        data = _json_root(text)
        cur = data
        *path, last = key.split(".")
        for k in path:
            cur = cur.setdefault(k, {})
        cur[last] = value
        return json.dumps(data, indent=2) + "\n", old
    cp = _ini(text)
    sec, _, k = key.partition(".")
    if not cp.has_section(sec):
        cp.add_section(sec)
    cp.set(sec, k, value)
    buf = io.StringIO()
    cp.write(buf)
    return buf.getvalue(), old
