import docker
import docker.errors
from docker.types import DeviceRequest


class DockerManager:
    def __init__(self, network_name: str = "selkies-hub"):
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
    ) -> str:
        kwargs: dict = {
            "name": name,
            "image": image,
            "labels": labels,
            "environment": environment,
            "volumes": volumes,
            "detach": True,
            "network": self._network_name,
            "ports": {f"{port}/tcp": None},
            "privileged": privileged,
        }
        if gpu_enabled:
            kwargs["device_requests"] = [
                DeviceRequest(count=gpu_count, capabilities=[["gpu"]])
            ]
            kwargs["environment"]["NVIDIA_DRIVER_CAPABILITIES"] = "all"
        if memory_limit:
            kwargs["mem_limit"] = memory_limit
        if shm_size:
            kwargs["shm_size"] = shm_size

        container = self._client.containers.create(**kwargs)
        return container.id

    def start_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.start()

    def stop_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.stop()

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
