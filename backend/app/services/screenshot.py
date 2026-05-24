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

            # Try HTTPS first (Selkies containers use self-signed HTTPS)
            for scheme in ("https", "http"):
                try:
                    resp = httpx.get(
                        f"{scheme}://{ip}:{port}/screenshot",
                        timeout=5,
                        verify=False,
                    )
                    if resp.status_code == 200 and len(resp.content) > 100:
                        path = self._cache_dir / f"{instance_id}.png"
                        path.write_bytes(resp.content)
                        return True
                except httpx.HTTPError:
                    continue

            # Fallback: try docker exec with grim (Wayland screenshot tool)
            try:
                exit_code, output = container.exec_run(
                    "grim -t png /tmp/screenshot.png",
                    environment={"XDG_RUNTIME_DIR": "/run/user/1000", "WAYLAND_DISPLAY": "wayland-0"},
                )
                if exit_code == 0:
                    bits, _ = container.get_archive("/tmp/screenshot.png")
                    # Docker get_archive returns a tar stream
                    import tarfile
                    import io
                    tar_stream = io.BytesIO(b"".join(bits))
                    with tarfile.open(fileobj=tar_stream) as tar:
                        member = tar.getmembers()[0]
                        f = tar.extractfile(member)
                        if f:
                            path = self._cache_dir / f"{instance_id}.png"
                            path.write_bytes(f.read())
                            return True
            except Exception:
                pass

            return False
        except Exception:
            return False

    def get_path(self, instance_id: str) -> Path | None:
        path = self._cache_dir / f"{instance_id}.png"
        if path.exists():
            return path
        return None
