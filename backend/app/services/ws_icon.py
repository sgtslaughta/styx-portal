"""Workstation icons: validation, storage format and server-side rendering.

Stored in Workstation.icon: None (auto badge), "emoji:<char>", or a
"data:<mime>;base64,..." image (PNG/SVG/ICO/WebP, <=256 KB decoded).
"""
import base64
import binascii
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from fastapi import Request, Response

MAX_IMAGE_BYTES = 256 * 1024
MAX_EMOJI_BYTES = 16
PALETTE = ["#2A767C", "#B88A3E", "#4F9A6C", "#B8432A", "#3D5A80", "#6B5B95"]
SVG_HEADERS = {"Content-Security-Policy":
               "default-src 'none'; style-src 'unsafe-inline'; sandbox"}

_DATA_URI = re.compile(r"^data:([a-z0-9.+/-]+);base64,([A-Za-z0-9+/=\s]+)$")
_SVG_NS = "{http://www.w3.org/2000/svg}"
_BAD_TAGS = {"style", "script", "foreignobject", "iframe", "object", "embed", "animate", "set"}
_ATTR_NS = {"http://www.w3.org/1999/xlink"}
_IMG_DATA = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]*$")
_BAD_FUNC = re.compile(r"@import|image-set|src\(|expression\(", re.I)
_URL = re.compile(r"url\(", re.I)
_LOCAL_URL = re.compile(r"url\(\s*(['\"]?)\s*#[^)'\"]*\1\s*\)", re.I)
_XML_NS = "http://www.w3.org/XML/1998/namespace"
# Editor metadata stripped (not rejected) before validation.
_EDITOR_NS = ("http://www.inkscape.org/namespaces/inkscape",
              "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
              "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
              "http://purl.org/dc/elements/1.1/",
              "http://purl.org/dc/terms/",
              "http://creativecommons.org/ns#",
              "http://web.resource.org/cc/")
_PLAIN = "Export as plain SVG (Inkscape: Save as \u203a Plain SVG) and try again."
ET.register_namespace("", _SVG_NS[1:-1])
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def _ns(name: str) -> str:
    return name[1:].split("}", 1)[0] if name.startswith("{") else ""


def _strip_editor_metadata(el) -> None:
    for child in list(el):
        tag = child.tag if isinstance(child.tag, str) else ""
        if _ns(tag) in _EDITOR_NS or (_ns(tag) == _SVG_NS[1:-1]
                                      and tag.endswith("}metadata")):
            el.remove(child)
        else:
            _strip_editor_metadata(child)
    for name in [n for n in el.attrib if _ns(n) in _EDITOR_NS]:
        del el.attrib[name]


def _bad_url(val: str) -> bool:
    """True unless every url( is a local #fragment reference."""
    return bool(_BAD_FUNC.search(val)) or (
        len(_URL.findall(val)) != len(_LOCAL_URL.findall(val)))
_DOCTYPE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.I)


_SVG_START = re.compile(rb"^(\xef\xbb\xbf)?\s*(<\?xml.*?\?>\s*|<!--.*?-->\s*)*(<svg|<!doctype)",
                        re.I | re.S)


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if _SVG_START.match(data[:16384]):
        return "image/svg+xml"
    return None


def _check_svg(data: bytes) -> bytes:
    """No defusedxml dependency (B314 nosec below): reject DTD/entities up front, then walk the
    tree refusing active content and any non-local reference. Editor metadata
    is stripped first; returns the cleaned serialization to store."""
    if _DOCTYPE.search(data) or b"<?xml-stylesheet" in data.lower():
        raise ValueError("SVG may not contain a DOCTYPE or entities")
    try:
        data.decode("utf-8")
        root = ET.fromstring(data)  # nosec B314
    except (ET.ParseError, UnicodeDecodeError):
        raise ValueError("Image is not valid SVG")
    if root.tag not in (f"{_SVG_NS}svg", "svg"):
        raise ValueError("Image is not valid SVG")
    _strip_editor_metadata(root)
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith(_SVG_NS):
            raise ValueError(f"SVG contains unsupported elements. {_PLAIN}")
        tag = el.tag[len(_SVG_NS):].lower()
        if tag in _BAD_TAGS:
            raise ValueError("SVG may not contain scripts or embedded content")
        if "\\" in (el.text or "") or "\\" in (el.tail or ""):
            raise ValueError("SVG may not contain escapes")
        for name, val in el.attrib.items():
            ns, _, local = name.rpartition("}")
            local = local.lower()
            if ns and ns[1:] not in _ATTR_NS and not (
                    ns[1:] == _XML_NS and local in ("space", "lang")):
                raise ValueError(f"SVG contains unsupported attributes. {_PLAIN}")
            squashed = re.sub(r"\s", "", val).lower()
            if local.startswith("on") or "javascript:" in squashed:
                raise ValueError("SVG may not contain scripts")
            if local == "href":
                if not (val.startswith("#") or (tag == "image" and _IMG_DATA.match(val))):
                    raise ValueError("SVG may not reference external resources")
            if "\\" in val:
                raise ValueError("SVG may not contain escapes")
            if _bad_url(val):
                raise ValueError("SVG may not reference external resources")
    return ET.tostring(root, encoding="utf-8")


def _is_one_grapheme(s: str) -> bool:
    clusters, prev, ri = 0, "", 0
    for ch in s:
        cat, cp = unicodedata.category(ch), ord(ch)
        if cat in ("Cc", "Cs", "Co", "Cn", "Zs", "Zl", "Zp"):
            return False
        extends = (cat in ("Mn", "Me", "Mc") or cp == 0x200D
                   or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F
                   or prev == "‍")
        if 0x1F1E6 <= cp <= 0x1F1FF:
            ri += 1
            extends = extends or ri % 2 == 0
        if not extends:
            clusters += 1
        prev = ch
    return clusters == 1


def _first_grapheme(s: str) -> str:
    best = ""
    for i in range(1, min(len(s), 64) + 1):
        if not _is_one_grapheme(s[:i]):
            break
        best = s[:i]
    return best or s[:1]


def validate_icon(kind: str, value: str | None) -> str | None:
    """Return the value to store (None = auto) or raise ValueError(plain message)."""
    if kind == "auto":
        return None
    if kind == "emoji":
        if not value or len(value.encode()) > MAX_EMOJI_BYTES or not _is_one_grapheme(value):
            raise ValueError("Icon must be a single emoji")
        return f"emoji:{value}"
    if kind != "image":
        raise ValueError("Unknown icon kind")
    m = _DATA_URI.match(value or "")
    if not m or len(value) > MAX_IMAGE_BYTES * 4 // 3 + 200:
        raise ValueError("Image must be a base64 data URI under 256 KB")
    try:
        data = base64.b64decode(re.sub(r"\s", "", m.group(2)), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Image is not valid base64")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image must be 256 KB or smaller")
    mime = _sniff(data)
    if mime is None:
        raise ValueError("Image must be PNG, SVG, ICO or WebP")
    if mime == "image/svg+xml":
        data = _check_svg(data)
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _svg(glyph: str, bg: str, font: int) -> bytes:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
        f'<rect width="64" height="64" rx="14" fill="{bg}"/>'
        f'<text x="32" y="32" text-anchor="middle" dominant-baseline="central" '
        f'font-family="system-ui,sans-serif" font-weight="600" font-size="{font}" '
        f'fill="#F4F1EA">{escape(glyph)}</text></svg>').encode()


def render_icon(icon: str | None, name: str, ws_id: str) -> tuple[bytes, str]:
    """(body, content-type). Only stored/derived values are emitted."""
    if icon and icon.startswith("data:"):
        m = _DATA_URI.match(icon)
        return base64.b64decode(m.group(2)), m.group(1)
    bg = PALETTE[int(hashlib.sha256(ws_id.encode()).hexdigest()[:8], 16) % len(PALETTE)]
    if icon and icon.startswith("emoji:"):
        return _svg(icon[6:], "#1F2430", 36), "image/svg+xml"
    return _svg((_first_grapheme(name.strip()) or "?").upper(), bg, 36), "image/svg+xml"


def icon_kind(icon: str | None) -> str:
    return "auto" if not icon else "emoji" if icon.startswith("emoji:") else "image"


def icon_etag(icon: str | None, name: str, ws_id: str) -> str:
    """Short hash; name only matters for the auto badge but is always mixed in."""
    return hashlib.sha256(f"{icon}\0{name}\0{ws_id}".encode()).hexdigest()[:16]


def icon_response(request: Request, icon: str | None, name: str, ws_id: str) -> Response:
    etag = f'"{icon_etag(icon, name, ws_id)}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=300",
               "X-Content-Type-Options": "nosniff"}
    inm = [t.strip().removeprefix("W/") for t in
           request.headers.get("if-none-match", "").split(",")]
    if etag in inm or "*" in inm:
        return Response(status_code=304, headers=headers)
    body, mime = render_icon(icon, name, ws_id)
    if mime == "image/svg+xml":
        headers.update(SVG_HEADERS)
    return Response(content=body, media_type=mime, headers=headers)
