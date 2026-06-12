import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import selkies_launcher  # noqa: E402


def test_patch_rewrites_wildcard_host_only():
    calls = []

    def fake_serve(handler, host, port, **kw):
        calls.append((host, port))
        return "server"

    patched = selkies_launcher._loopback_only(fake_serve)
    assert patched(None, "0.0.0.0", 8444) == "server"
    assert patched(None, "127.0.0.1", 9000) == "server"
    assert calls == [("127.0.0.1", 8444), ("127.0.0.1", 9000)]
