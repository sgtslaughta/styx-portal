import tempfile
from unittest.mock import MagicMock, patch
from pathlib import Path

from app.services.screenshot import ScreenshotService


def test_screenshot_cache_dir_created():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
        assert Path(tmpdir).is_dir()


@patch("app.services.screenshot.httpx")
def test_capture_screenshot(mock_httpx):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"\x89PNG fake image data"
    mock_httpx.get.return_value = mock_response

    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "selkies-hub": {"IPAddress": "172.18.0.5"}
            }
        }
    }
    mock_docker._client.containers.get.return_value = mock_container

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=mock_docker)
        result = svc.capture("instance-123", "container-abc", 3001)

        assert result is True
        cached = Path(tmpdir) / "instance-123.png"
        assert cached.exists()
        assert cached.read_bytes() == b"\x89PNG fake image data"


@patch("app.services.screenshot.httpx")
def test_capture_screenshot_failure(mock_httpx):
    mock_httpx.get.side_effect = Exception("connection refused")
    mock_docker = MagicMock()
    mock_container = MagicMock()
    mock_container.attrs = {
        "NetworkSettings": {
            "Networks": {
                "selkies-hub": {"IPAddress": "172.18.0.5"}
            }
        }
    }
    mock_docker._client.containers.get.return_value = mock_container

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=mock_docker)
        result = svc.capture("inst-1", "cont-1", 3001)
        assert result is False


def test_get_screenshot_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())

        assert svc.get_path("nonexistent") is None

        cached = Path(tmpdir) / "inst-1.png"
        cached.write_bytes(b"\x89PNG data")
        assert svc.get_path("inst-1") == cached
