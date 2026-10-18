import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portal_api  # noqa: E402


def test_api_bytes_normalises_weak_quoted_etag():
    resp = MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = b"x"
    resp.headers = {"Content-Type": "image/png; charset=x", "ETag": 'W/"abc"'}
    with patch.object(portal_api.urllib.request, "urlopen", return_value=resp):
        out = portal_api.api_bytes({"server": "http://s", "agent_token": "t"}, "/p")
    assert out == (b"x", "image/png", "abc")
