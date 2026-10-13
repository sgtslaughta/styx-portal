import base64

import pytest

from app.services import ws_icon

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
ICO = b"\x00\x00\x01\x00" + b"0" * 20
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 20
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8"/></svg>'


def uri(data: bytes, mime="image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


@pytest.mark.parametrize("data,mime", [(PNG, "image/png"), (ICO, "image/x-icon"),
                                       (WEBP, "image/webp"), (SVG, "image/svg+xml")])
def test_good_images_accepted(data, mime):
    out = ws_icon.validate_icon("image", uri(data, mime))
    assert out.startswith(f"data:{mime};base64,")


def test_mime_is_taken_from_magic_not_claim():
    assert ws_icon.validate_icon("image", uri(PNG, "image/svg+xml")).startswith("data:image/png;")


@pytest.mark.parametrize("value", [
    uri(b"GIF89a" + b"0" * 20), uri(b"not an image"), "notauri", "data:image/png;base64,@@@",
    uri(PNG + b"0" * (256 * 1024)),
])
def test_bad_images_rejected(value):
    with pytest.raises(ValueError):
        ws_icon.validate_icon("image", value)


@pytest.mark.parametrize("svg", [
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" onload="x()"/>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink"><image x:href="http://evil/x.png"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://evil/x.png"/></svg>',
    b'<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(http://evil/a.css);</style></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" style="fill:url(http://evil/a)"/>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><h:img xmlns:h="http://www.w3.org/1999/xhtml" src="http://e/x"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><h:meta xmlns:h="http://www.w3.org/1999/xhtml" http-equiv="refresh" content="0;url=http://e"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect style="fill:\\75rl(http://e/a)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><style>@\\69mport "http://e/a.css";</style></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" onLoad="x()"/>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><a href="&#106;avascript:alert(1)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink"><a x:href="javascript:alert(1)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><use href="data:image/svg+xml,%3Csvg/%3E"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><image href="data:image/svg+xml;base64,AAAA"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><style><desc/>@import url(http://e/a.css);</style></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><style>rect{fill:red}</style></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="\\75rl(http://e/a)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect filter="\\75 rl(http://e/a)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect style="background:image-set(\'http://e\' 1x)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(#a) url(http://e/b)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" xml:base="http://e/"/>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(\'http://e\')"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(#a)url(http://x)"/></svg>',
    b'<svg xmlns="http://www.w3.org/2000/svg" xml:id="a"/>',
    b'<html/>', b'<svg', b'\xff\xfe<svg/>',
])
def test_bad_svg_rejected(svg):
    with pytest.raises(ValueError):
        ws_icon.validate_icon("image", uri(svg, "image/svg+xml"))


def test_svg_internal_refs_ok():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g"/></defs>'
           b'<rect fill="url(#g)"/><use href="#g"/></svg>')
    ws_icon.validate_icon("image", uri(svg, "image/svg+xml"))


@pytest.mark.parametrize("e", ["\U0001F680", "\U0001F468\u200d\U0001F4BB",
                               "\U0001F44D\U0001F3FD", "\U0001F1E9\U0001F1EA", "\u2764\ufe0f", "A"])
def test_good_emoji(e):
    assert ws_icon.validate_icon("emoji", e) == f"emoji:{e}"


@pytest.mark.parametrize("e", ["", "ab", "\U0001F680\U0001F680", "x" * 40, "\n", "‍"])
def test_bad_emoji(e):
    with pytest.raises(ValueError):
        ws_icon.validate_icon("emoji", e)


def test_auto_clears_and_unknown_kind():
    assert ws_icon.validate_icon("auto", None) is None
    with pytest.raises(ValueError):
        ws_icon.validate_icon("bogus", "x")


def test_auto_svg_deterministic_color_and_letter():
    a1, _ = ws_icon.render_icon(None, "desk", "id-1")
    a2, _ = ws_icon.render_icon(None, "other", "id-1")
    assert a1.count(b"fill=\"#") and a1.split(b'fill="')[1][:7] == a2.split(b'fill="')[1][:7]
    assert b">D<" in a1 and b">O<" in a2
    assert a1.split(b'fill="')[1][:7].decode() in ws_icon.PALETTE


def test_auto_svg_escapes_name():
    body, mime = ws_icon.render_icon(None, "<script>", "i")
    assert mime == "image/svg+xml" and b"<script" not in body and b"&lt;" in body


def test_emoji_and_image_render():
    body, mime = ws_icon.render_icon("emoji:\U0001F680", "n", "i")
    assert mime == "image/svg+xml" and "\U0001F680".encode() in body
    body, mime = ws_icon.render_icon(uri(PNG), "n", "i")
    assert (body, mime) == (PNG, "image/png")


def test_etag_changes_with_icon_name_id():
    base = ws_icon.icon_etag(None, "n", "i")
    assert base != ws_icon.icon_etag("emoji:x", "n", "i")
    assert base != ws_icon.icon_etag(None, "m", "i")
    assert base == ws_icon.icon_etag(None, "n", "i")


def test_normal_svg_accepted():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><title>t</title>'
           b'<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
           b'<path d="M0 0h8v8z" fill="url(#g)"/>'
           b'<image href="data:image/png;base64,AAAA"/></svg>')
    ws_icon.validate_icon("image", uri(svg, "image/svg+xml"))


def test_svg_csp_has_sandbox():
    assert "sandbox" in ws_icon.SVG_HEADERS["Content-Security-Policy"]


@pytest.mark.parametrize("fill", ["url('#g')", "url( #a )", 'url("#a")', "url(#a) url(#b)"])
def test_quoted_local_url_and_xml_space_accepted(fill):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" xml:lang="en">'
           f'<rect fill="{fill.replace(chr(34), "&quot;")}"/></svg>').encode()
    ws_icon.validate_icon("image", uri(svg, "image/svg+xml"))


INKSCAPE = b"""<?xml version="1.0" encoding="UTF-8"?>
<!-- Created with Inkscape -->
<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
 xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
 xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:cc="http://creativecommons.org/ns#" inkscape:version="1.3" sodipodi:docname="a.svg" viewBox="0 0 8 8">
<sodipodi:namedview id="nv" inkscape:zoom="2"/>
<metadata id="m"><rdf:RDF><cc:Work rdf:about=""><dc:title>x</dc:title></cc:Work></rdf:RDF></metadata>
<rect inkscape:label="r" width="8" height="8" fill="url('#g')"/></svg>"""


def test_inkscape_svg_accepted_and_stored_clean():
    out = ws_icon.validate_icon("image", uri(INKSCAPE, "image/svg+xml"))
    stored = base64.b64decode(out.split(",", 1)[1]).decode()
    for bad in ("sodipodi", "inkscape", "rdf", "dc:", "metadata", "cc:", "purl.org"):
        assert bad not in stored
    assert "<rect" in stored and 'xmlns="http://www.w3.org/2000/svg"' in stored


def test_xhtml_element_rejected_with_actionable_message():
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg"><h:b xmlns:h="http://www.w3.org/1999/xhtml"/></svg>')
    with pytest.raises(ValueError, match="Plain SVG"):
        ws_icon.validate_icon("image", uri(svg, "image/svg+xml"))


def test_svg_sniffed_after_declaration_and_long_comment():
    svg = b'<?xml version="1.0"?>\n<!--' + b"c" * 6000 + b'-->\n' + SVG
    assert ws_icon.validate_icon("image", uri(svg, "image/svg+xml")).startswith("data:image/svg+xml")


def test_auto_badge_uses_first_grapheme():
    body, _ = ws_icon.render_icon(None, "\U0001F469‍\U0001F4BB lab", "i")
    assert "\U0001F469‍\U0001F4BB".encode() in body and b"lab" not in body
    body, _ = ws_icon.render_icon(None, "éclair", "i")
    assert "É".encode() in body or "É".encode() in body


def test_sniff_prolog_scan_is_linear():
    import time
    t = time.perf_counter()
    assert ws_icon._sniff(b"<!--" * 4096) is None
    assert ws_icon._sniff(b"<?xml " * 2700) is None
    assert time.perf_counter() - t < 0.2


def test_sniff_prolog_comment_then_svg():
    data = b'\xef\xbb\xbf <?xml version="1.0"?>\n<!-- a -->\n <!-- b -->\n<svg xmlns="x"/>'
    assert ws_icon._sniff(data) == "image/svg+xml"
    assert ws_icon._sniff(b"<!DOCTYPE svg>") == "image/svg+xml"


@pytest.mark.parametrize("unit", [b"<?xml?>", b"<!---->"])
def test_sniff_reviewer_redos_cases(unit):
    import time
    t = time.perf_counter()
    assert ws_icon._sniff(unit * 2000 + b"x") is None
    assert time.perf_counter() - t < 0.2
