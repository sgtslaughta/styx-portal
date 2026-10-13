"""GNOME logical scale for the headless seat: pure helpers here; apply_scale (DisplayConfig) is added with the seat helper."""
import os
from pathlib import Path


def scale_for_dpi(dpi) -> int:
    # ponytail: integer scales only; Mutter offers [1.0, 2.0] without the fractional experimental feature.
    # 168 = midpoint of 96 and 240.
    return 2 if dpi and dpi >= 168 else 1


def read_scale(path) -> int:
    try:
        return 2 if Path(path).read_text().strip() == "2" else 1
    except OSError:
        return 1


def write_scale(path, s) -> None:
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(str(int(s)))
    os.replace(tmp, p)
