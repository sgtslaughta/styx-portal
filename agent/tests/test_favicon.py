import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import favicon  # noqa: E402
from gateway_html import inject_favicon  # noqa: E402


def _fetch(body=b"PNGDATA", ctype="image/png", etag="e1", calls=None):
    def f(cfg, path):
        if calls is not None:
            calls.append(path)
        return body, ctype, etag
    return f


def test_writes_on_new_etag(tmp_path):
    calls = []
    assert favicon.sync({}, tmp_path, "e1", fetch=_fetch(calls=calls))
    assert favicon.read(tmp_path) == (b"PNGDATA", "image/png", "e1")
    assert calls == ["/api/agent/icon"]
    assert not list(tmp_path.glob("*.tmp"))


def test_no_fetch_when_etag_unchanged_or_empty(tmp_path):
    favicon.sync({}, tmp_path, "e1", fetch=_fetch())
    calls = []
    assert not favicon.sync({}, tmp_path, "e1", fetch=_fetch(calls=calls))
    assert not favicon.sync({}, tmp_path, "", fetch=_fetch(calls=calls))
    assert calls == []


def test_rewrites_when_etag_changes(tmp_path):
    favicon.sync({}, tmp_path, "e1", fetch=_fetch())
    favicon.sync({}, tmp_path, "e2", fetch=_fetch(b"NEW", "image/svg+xml", "e2"))
    assert favicon.read(tmp_path) == (b"NEW", "image/svg+xml", "e2")


def test_fetch_failure_is_swallowed_and_keeps_old_cache(tmp_path, capsys):
    favicon.sync({}, tmp_path, "e1", fetch=_fetch())

    def boom(cfg, path):
        raise OSError("down")
    assert favicon.sync({}, tmp_path, "e2", fetch=boom) is False
    assert favicon.read(tmp_path)[2] == "e1"
    assert "favicon sync failed" in capsys.readouterr().out


def test_rejects_bad_type_and_oversize(tmp_path):
    assert not favicon.sync({}, tmp_path, "e1", fetch=_fetch(ctype="text/html"))
    assert not favicon.sync({}, tmp_path, "e1",
                            fetch=_fetch(b"x" * (favicon.MAX_BYTES + 1)))
    assert favicon.read(tmp_path) is None


def test_read_missing_is_none(tmp_path):
    assert favicon.read(tmp_path) is None


def test_inject_favicon_shim_and_json_escaping():
    out = inject_favicon("<html><head></head></html>", 'a"</script><b>')
    assert '/styx-favicon?v=' in out
    assert '</script><b>' not in out and '\\u003c' in out
    assert out.index("<script>") < out.index("</head>")
    assert "MutationObserver" in out and "apple-touch-icon" in out


def test_inject_favicon_without_head():
    assert inject_favicon("<p>x</p>", "e").startswith("<script>")
