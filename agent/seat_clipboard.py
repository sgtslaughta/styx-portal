"""GNOME seat clipboard server (system python, inside seat_portal's GLib loop).

Mutter has no wlr/ext data-control, so selkies cannot reach the seat's
clipboard itself. This serves it from the RemoteDesktop session's clipboard
API over a unix socket; engine.seat_selkies_main points selkies' app
clipboard calls here. Every flavour passes through: text, html, images.

Protocol: one JSON request line per connection, then the client shuts down
its write side. Reply is b"+" + payload, or b"-" + error text.
  {"op": "types"}                             -> JSON list of mime types
  {"op": "read", "mime": m}                   -> raw bytes
  {"op": "write", "offers": [[m, b64], ...]}  -> empty
  {"op": "watch"}                             -> then one JSON mime list per line per change
"""
import base64
import json
import os
import select
import socket

from gi.repository import GLib

from engine import clip_socket_path

CAP = 64 << 20          # bytes per flavour; bigger selections are truncated


def log(*a):
    print("[seat-clipboard]", *a, flush=True)


def read_fd(fd: int, timeout: float = 2.0) -> bytes:
    """Drain a selection pipe; a stalled owner gives up after `timeout`."""
    out = bytearray()
    with os.fdopen(fd, "rb", buffering=0) as f:
        while len(out) < CAP and select.select([f], [], [], timeout)[0]:
            chunk = f.read(65536)
            if not chunk:
                break
            out += chunk
    return bytes(out)


def _recv_all(conn: socket.socket) -> bytes:
    return b"".join(iter(lambda: conn.recv(65536), b""))


class ClipboardServer:
    """`rd` is the Mutter RemoteDesktop.Session proxy; `on_signal(handler,
    member)` subscribes to one of its signals and returns a removable match."""

    def __init__(self, rd, on_signal, path: str | None = None):
        self.rd = rd
        self.mimes: list[str] = []          # flavours of a seat app's selection
        self.owned: dict[str, bytes] = {}   # our selection (a viewer's copy)
        self.watchers: list[socket.socket] = []
        rd.EnableClipboard({})
        self.rx = [on_signal(self._owner, "SelectionOwnerChanged"),
                   on_signal(self._transfer, "SelectionTransfer")]
        self.path = path or clip_socket_path()
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.bind(self.path)
        os.chmod(self.path, 0o600)
        self.ino = os.stat(self.path).st_ino
        self.sock.listen(8)
        self.src = GLib.io_add_watch(self.sock.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN,
                                      self._accept)
        log("serving", self.path)

    # Mutter -> us
    def _owner(self, options):
        if options.get("session-is-owner"):
            return                          # our own SetSelection
        self.owned = {}
        self.mimes = [str(m) for m in options.get("mime-types", [])]
        line = json.dumps(self.mimes).encode() + b"\n"
        for w in list(self.watchers):
            try:
                w.sendall(line)
            except OSError:
                self.watchers.remove(w)
                w.close()

    def _transfer(self, mime, serial):
        data = self.owned.get(str(mime))
        ok = data is not None
        if data is not None:
            try:
                with os.fdopen(self.rd.SelectionWrite(serial).take(), "wb") as f:
                    f.write(data)
            except Exception as e:          # OSError or D-Bus
                log("write failed:", e)
                ok = False
        self.rd.SelectionWriteDone(serial, ok)

    # selkies -> us
    def handle(self, req: dict, conn: socket.socket) -> bytes | None:
        op = req.get("op")
        if op == "types":
            return b"+" + json.dumps(list(self.owned) or self.mimes).encode()
        if op == "read":
            mime = str(req["mime"])
            if self.owned:                  # never ask Mutter: it would ask us back
                if mime not in self.owned:
                    raise KeyError(mime)
                return b"+" + self.owned[mime]
            if mime not in self.mimes:
                raise KeyError(mime)
            return b"+" + read_fd(self.rd.SelectionRead(mime).take())
        if op == "write":
            offers = {str(m): base64.b64decode(d) for m, d in req["offers"]}
            if offers:
                self.owned = offers
                self.rd.SetSelection({"mime-types": list(offers)})
            return b"+"
        if op == "watch":
            conn.sendall(b"+")
            self.watchers.append(conn)
            return None                     # kept open
        raise ValueError(f"bad op {op!r}")

    def _accept(self, *_):
        conn, _ = self.sock.accept()
        conn.settimeout(5)
        try:
            reply = self.handle(json.loads(_recv_all(conn)), conn)
        except Exception as e:              # bad request, D-Bus or pipe error
            reply = b"-" + f"{type(e).__name__}: {e}".encode()
        if reply is not None:
            try:
                conn.sendall(reply)
            except OSError:
                pass
            conn.close()
        return True

    def stop(self):
        GLib.source_remove(self.src)
        for r in self.rx:
            r.remove()
        for w in self.watchers:
            w.close()
        self.sock.close()
        try:
            if os.stat(self.path).st_ino == self.ino:   # a newer session may own it
                os.unlink(self.path)
        except FileNotFoundError:
            pass
