import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ab  # noqa: E402


def test_foreign_client_detected():
    lines = [
        "2026-10-30 16:24:32 gateway: ws open vid=1 role=controller from=127.0.0.1 (n=1)",
        "2026-10-30 16:24:39 gateway: ws open vid=2 role=controller from=12.202.23.216 (n=2)",
    ]
    assert ab.foreign_client(lines) == "12.202.23.216"
    assert ab.foreign_client(lines[:1]) is None
    assert ab.foreign_client(["gateway: ws close vid=2 code=1006 from=12.0.0.1"]) is None


def test_av1_16_variant():
    assert ab.VARIANTS["av1-16"][0].startswith("--encoder=av1enc,h265enc,h264enc")
