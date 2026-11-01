import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import xwl_eager  # noqa: E402


def test_so_matches_hash_and_exports_symbol(tmp_path):
    out = xwl_eager.write_so(tmp_path / "x.so")
    data = out.read_bytes()
    assert hashlib.sha256(data).hexdigest() == xwl_eager.SO_SHA256
    assert data.startswith(b"\x7fELF") and b"sd_pid_get_user_unit" in data
    assert (out.stat().st_mode & 0o777) == 0o644


def test_write_so_skips_unchanged(tmp_path):
    p = tmp_path / "x.so"
    xwl_eager.write_so(p)
    os.utime(p, (1000, 1000))
    xwl_eager.write_so(p)
    assert p.stat().st_mtime == 1000
    p.write_bytes(b"junk")
    xwl_eager.write_so(p)
    assert hashlib.sha256(p.read_bytes()).hexdigest() == xwl_eager.SO_SHA256
