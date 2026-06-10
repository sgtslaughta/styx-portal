import os
from pathlib import Path

import docker
import docker.errors
from docker.types import DeviceRequest


def detect_gpu() -> dict:
    """Detect available GPU on host."""
    result = {"available": False, "type": None, "devices": []}

    dri_path = Path("/dev/dri")
    if dri_path.exists():
        devices = [str(d) for d in dri_path.iterdir()]
        if devices:
            result["available"] = True
            result["devices"] = devices
            # Check for NVIDIA
            if Path("/dev/nvidia0").exists() or os.path.exists("/proc/driver/nvidia"):
                result["type"] = "nvidia"
            else:
                result["type"] = "intel/amd"

    # Also check for NVIDIA without /dev/dri
    if not result["available"] and Path("/dev/nvidia0").exists():
        result["available"] = True
        result["type"] = "nvidia"
        result["devices"] = ["/dev/nvidia0"]

    return result


class DockerManager:
    def __init__(self, network_name: str = "styx-portal"):
        self._client = docker.DockerClient.from_env()
        self._network_name = network_name

    def create_container(
        self,
        name: str,
        image: str,
        labels: dict[str, str],
        environment: dict[str, str],
        volumes: dict[str, dict],
        port: int,
        gpu_enabled: bool = False,
        gpu_count: int = 1,
        memory_limit: str | None = None,
        cpu_limit: str | None = None,
        shm_size: str | None = None,
        privileged: bool = False,
        dind: bool = False,
        cap_add: list[str] | None = None,
        security_opt: list[str] | None = None,
    ) -> str:
        if dind:
            privileged = True
            environment = {**environment, "START_DOCKER": "true"}
            if not memory_limit or not cpu_limit:
                raise ValueError(
                    "DinD templates require explicit resource limits (memory + cpu)"
                )

        kwargs: dict = {
            "name": name,
            "image": image,
            "labels": labels,
            "environment": {"PIXELFLUX_WAYLAND": "true", **environment},
            "volumes": volumes,
            "detach": True,
            "network": self._network_name,
            "privileged": privileged,
        }
        if privileged:
            # privileged grants all caps; cap flags would be rejected
            kwargs["security_opt"] = list(security_opt or [])
        else:
            kwargs["security_opt"] = ["no-new-privileges:true"] + list(security_opt or [])
            kwargs["cap_drop"] = ["ALL"]
            kwargs["cap_add"] = list(cap_add or [])
        if gpu_enabled:
            gpu_info = detect_gpu()
            if gpu_info["type"] == "nvidia":
                kwargs["device_requests"] = [
                    DeviceRequest(
                        count=gpu_count,
                        capabilities=[["compute", "video", "graphics", "utility"]],
                    )
                ]
                kwargs["environment"]["NVIDIA_DRIVER_CAPABILITIES"] = "all"
                kwargs["environment"]["NVIDIA_VISIBLE_DEVICES"] = "all"
            # Mount /dev/dri for Intel/AMD/VA-API
            if Path("/dev/dri").exists():
                kwargs["devices"] = ["/dev/dri:/dev/dri"]
            # Auto GPU detection env for Selkies containers
            kwargs["environment"]["AUTO_GPU"] = "true"

        if memory_limit:
            kwargs["mem_limit"] = memory_limit
        if shm_size:
            kwargs["shm_size"] = shm_size
        if cpu_limit:
            kwargs["nano_cpus"] = int(float(cpu_limit) * 1e9)

        try:
            self._client.images.get(image)
        except docker.errors.ImageNotFound:
            if "/" not in image:
                raise
            self._client.images.pull(image)

        container = self._client.containers.create(**kwargs)
        return container.id

    def image_exists(self, image: str) -> bool:
        try:
            self._client.images.get(image)
            return True
        except docker.errors.ImageNotFound:
            return False

    def start_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.start()

    def stop_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.stop()

    def pause_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.pause()

    def unpause_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.unpause()

    def restart_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.restart()

    def remove_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.remove(force=True)

    def get_container_status(self, container_id: str) -> dict:
        try:
            container = self._client.containers.get(container_id)
            return {
                "status": container.status,
                "started_at": container.attrs["State"]["StartedAt"],
            }
        except docker.errors.NotFound:
            return {"status": "not_found"}

    def get_container_stats(self, container_id: str) -> dict:
        try:
            container = self._client.containers.get(container_id)
            return container.stats(stream=False)
        except docker.errors.NotFound:
            return {}

    def create_volume(self, name: str) -> str:
        volume = self._client.volumes.create(name=name)
        return volume.name

    def remove_volume(self, name: str) -> None:
        volume = self._client.volumes.get(name)
        volume.remove()

    def remove_image(self, image: str) -> None:
        self._client.images.remove(image, force=True)

    def get_image_info(self, image: str) -> dict | None:
        try:
            img = self._client.images.get(image)
            size_mb = img.attrs.get("Size", 0) // (1024 * 1024)
            return {"size_mb": size_mb, "id": img.id}
        except docker.errors.ImageNotFound:
            return None
