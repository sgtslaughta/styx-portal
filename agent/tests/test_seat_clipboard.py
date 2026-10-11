"""seat_clipboard <-> engine client round trip against a fake Mutter session."""
import json
import os
import socket
import threading

import pytest

pytest.importorskip("gi")              # system python on seat boxes; skipped elsewhere

import engine  # noqa: E402
import seat_clipboard  # noqa: E402


class FakeFd:
    def __init__(self, fd):
        self.fd = fd

    def take(self):
        return self.fd


class FakeRD:
    def __init__(self):
        self.selection, self.written = None, {}

    def EnableClipboard(self, _o): pass

    def SetSelection(self, o): self.selection = o["mime-types"]

    def SelectionRead(self, mime):
        r, w = os.pipe()
        os.write(w, b"<b>hi</b>" if mime == "text/html" else b"\x89PNG")
        os.close(w)
        return FakeFd(r)

    def SelectionWrite(self, serial):
        r, w = os.pipe()
        self.written[serial] = r
        return FakeFd(w)

    def SelectionWriteDone(self, serial, ok): self.done = (serial, ok)


class Match:
    def remove(self): pass


def _serve(srv, req, path):
    """Client in a thread, one accept on the server side."""
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("r", _try(req, path)))
    t.start()
    srv._accept()
    t.join(5)
    return out["r"]


def _try(req, path):
    try:
        return engine.clip_call(req, path)
    except RuntimeError as e:
        return e


def test_round_trip_all_flavours(tmp_path):
    rd, sigs = FakeRD(), {}
    path = str(tmp_path / "clip.sock")
    srv = seat_clipboard.ClipboardServer(
        rd, lambda fn, member: sigs.setdefault(member, fn) and Match(), path)
    try:
        # a seat app copies html + png
        sigs["SelectionOwnerChanged"]({"mime-types": ["text/html", "image/png"]})
        assert json.loads(_serve(srv, {"op": "types"}, path)) == ["text/html", "image/png"]
        assert _serve(srv, {"op": "read", "mime": "image/png"}, path) == b"\x89PNG"
        assert isinstance(_serve(srv, {"op": "read", "mime": "nope"}, path), RuntimeError)

        # a viewer copies; Mutter asks us for it
        import base64
        offers = [["text/plain", base64.b64encode(b"yo").decode()],
                  ["image/png", base64.b64encode(b"IMG").decode()]]
        assert _serve(srv, {"op": "write", "offers": offers}, path) == b""
        assert rd.selection == ["text/plain", "image/png"]
        sigs["SelectionOwnerChanged"]({"mime-types": rd.selection, "session-is-owner": True})
        sigs["SelectionTransfer"]("image/png", 7)
        assert os.read(rd.written[7], 10) == b"IMG" and rd.done == (7, True)
        # reads of our own selection never round-trip through Mutter
        assert _serve(srv, {"op": "read", "mime": "text/plain"}, path) == b"yo"
        newer = seat_clipboard.ClipboardServer(FakeRD(), lambda fn, m: Match(), path)
    finally:
        srv.stop()                          # must not unlink the newer server's socket
    assert os.path.exists(path)
    newer.stop()
    assert not os.path.exists(path)
    with pytest.raises(OSError):
        socket.socket(socket.AF_UNIX).connect(path)
