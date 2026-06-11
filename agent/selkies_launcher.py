#!/usr/bin/env python3
"""Run selkies with every websocket server bound to loopback.

Upstream hardcodes '0.0.0.0' (selkies.py run_server). The LAN-facing port
is owned by gateway.py, which enforces basic auth; selkies itself must only
be reachable through it. Patching serve() at import time covers the data
websocket and any future listener uniformly.

Import analysis:
  - selkies.py: imports "websockets.asyncio.server as ws_async", uses ws_async.serve()
  - signaling_server.py: imports "websockets.asyncio.server", uses websockets.asyncio.server.serve()

Since signaling_server uses the full module path (not a module alias), patching
only the alias won't affect it. We patch websockets.asyncio.server.serve directly
before any selkies imports occur.
"""
import functools
import sys


def _loopback_only(serve):
    @functools.wraps(serve)
    def wrapper(handler, host, port, **kw):
        return serve(handler, "127.0.0.1", port, **kw)
    return wrapper


def main() -> None:
    import websockets.asyncio.server as ws_async
    # Patch at the module level so both direct imports and aliases see it
    ws_async.serve = _loopback_only(ws_async.serve)

    # Now import selkies modules; they will get the patched serve
    from selkies.__main__ import main as selkies_main
    sys.argv[0] = "selkies"
    selkies_main()


if __name__ == "__main__":
    main()
