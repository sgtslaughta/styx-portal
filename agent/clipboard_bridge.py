#!/usr/bin/env python3
"""Bidirectional clipboard mirror between two Wayland sockets.

Seat mode runs two nested compositors: pixelflux (the streamed display, where
selkies' wl-copy/wl-paste operate) and labwc (where the desktop apps live).
Their clipboards are independent, so client<->remote copy/paste silently fails.
This daemon polls both clipboards and mirrors changes across, deduping by
content so a propagated value doesn't echo back into a loop.

Usage: clipboard_bridge.py <socket_a> <socket_b> <runtime_dir> [poll_s]
"""
import subprocess
import sys
import time

WL_PASTE = "wl-paste"
WL_COPY = "wl-copy"


def _env(socket: str, runtime_dir: str) -> dict:
    """Environment for running wl-paste/wl-copy in a specific socket."""
    return {
        "WAYLAND_DISPLAY": socket,
        "XDG_RUNTIME_DIR": runtime_dir,
        "PATH": "/usr/bin:/bin",
    }


def read_clip(socket: str, runtime_dir: str) -> str | None:
    """Read clipboard from the specified Wayland socket.

    Returns the clipboard content or None if empty/unavailable.
    wl-paste exits non-zero when the clipboard is empty; we treat that as None.
    """
    try:
        r = subprocess.run(
            [WL_PASTE, "-n", "-t", "text/plain"],
            env=_env(socket, runtime_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None  # empty clipboard exits non-zero; treat as no value
    return r.stdout


def write_clip(socket: str, runtime_dir: str, text: str) -> None:
    """Write text to the clipboard on the specified Wayland socket.

    Silently ignores errors (compositor may not be ready).
    """
    try:
        subprocess.run(
            [WL_COPY, "-t", "text/plain"],
            input=text,
            env=_env(socket, runtime_dir),
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def bridge_decision(a: str | None, b: str | None, last_a: str | None, last_b: str | None) -> tuple[str, str] | None:
    """Pure: decide what to mirror based on clipboard state.

    Returns ('a->b', value) | ('b->a', value) | None.

    Logic: propagate the side that CHANGED since last tick, unless both
    already match (no sync needed). If both changed, deterministically prefer
    a->b (rare race, both users typed). Dedup by content prevents the
    propagated value from echoing back in the next tick.
    """
    if a == b:
        # Already equal; no sync needed
        return None

    a_changed = a != last_a
    b_changed = b != last_b

    if a_changed and not b_changed:
        return ("a->b", a)
    if b_changed and not a_changed:
        return ("b->a", b)
    if a_changed and b_changed:
        # Both changed in the same tick (rare): prefer a->b deterministically
        return ("a->b", a)

    return None


def run(socket_a: str, socket_b: str, runtime_dir: str, poll_s: float = 1.0) -> None:
    """Poll clipboards and mirror changes until killed."""
    last_a = last_b = None
    while True:
        a = read_clip(socket_a, runtime_dir)
        b = read_clip(socket_b, runtime_dir)
        decision = bridge_decision(a, b, last_a, last_b)
        if decision:
            direction, val = decision
            if val is not None:
                if direction == "a->b":
                    write_clip(socket_b, runtime_dir, val)
                else:
                    write_clip(socket_a, runtime_dir, val)
            # Always advance state after a decision, even when val is None
            last_a = last_b = val
        else:
            # No propagation; track the current state for next tick
            last_a, last_b = a, b
        time.sleep(poll_s)


def main() -> None:
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <socket_a> <socket_b> <runtime_dir> [poll_s]", file=sys.stderr)
        sys.exit(1)

    socket_a, socket_b, runtime_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    poll_s = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    run(socket_a, socket_b, runtime_dir, poll_s)


if __name__ == "__main__":
    main()
