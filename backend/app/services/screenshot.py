from pathlib import Path

import httpx

from app.services.docker_manager import DockerManager


class ScreenshotService:
    def __init__(self, cache_dir: str, docker_manager: DockerManager):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._docker = docker_manager

    def capture(self, instance_id: str, container_id: str, port: int) -> bool:
        try:
            container = self._docker._client.containers.get(container_id)
            networks = container.attrs["NetworkSettings"]["Networks"]
            ip = None
            for net in networks.values():
                ip = net.get("IPAddress")
                if ip:
                    break
            if not ip:
                return False

            resp = httpx.get(f"http://{ip}:{port}/screenshot", timeout=10)
            if resp.status_code != 200:
                return False

            path = self._cache_dir / f"{instance_id}.png"
            path.write_bytes(resp.content)
            return True
        except Exception:
            return False

    def get_path(self, instance_id: str) -> Path | None:
        path = self._cache_dir / f"{instance_id}.png"
        if path.exists():
            return path
        return None
