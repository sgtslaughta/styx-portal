import os
from pathlib import Path

import docker
import docker.errors
from docker.types import DeviceRequest, Ulimit

from app.config import Settings

TRAEFIK_CONTAINER = "styx-traefik"

# Defense-in-depth: denylist of security-critical keys that extra_docker_args
# must never set, even if validation bypasses. These are enforced at the sink.
_EXTRA_DOCKER_ARGS_DENYLIST = {
    "privileged", "cap_add", "cap_drop", "security_opt", "devices",
    "device_requests", "network_mode", "network", "pid_mode",
    "ipc_mode", "userns_mode", "uts_mode", "binds", "volumes",
    "mounts", "volumes_from", "cgroup_parent", "sysctls",
    "restart_policy", "runtime", "device_cgroup_rules",
}


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
    def __init__(self, network_name: str = "styx-portal", base_url: str | None = None):
        url = base_url or Settings().DOCKER_SOCKET
        self._client = docker.DockerClient(base_url=url)
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
        network: str | None = None,
        restart_policy: str = "no",
        read_only_rootfs: bool = False,
        tmpfs: list[str] | None = None,
        extra_hosts: dict[str, str] | None = None,
        ulimits: list[dict] | None = None,
        devices: list[str] | None = None,
        entrypoint: list[str] | None = None,
        command: list[str] | None = None,
        extra_docker_args: dict | None = None,
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
            "network": network or self._network_name,
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

        if restart_policy and restart_policy != "no":
            kwargs["restart_policy"] = {"Name": restart_policy, "MaximumRetryCount": 0}
        if read_only_rootfs:
            kwargs["read_only"] = True
        if tmpfs:
            kwargs["tmpfs"] = {path: "" for path in tmpfs}
        if extra_hosts:
            kwargs["extra_hosts"] = dict(extra_hosts)
        if ulimits:
            kwargs["ulimits"] = [
                Ulimit(name=u["name"], soft=u.get("soft"), hard=u.get("hard"))
                for u in ulimits
            ]
        if devices:
            kwargs["devices"] = list(kwargs.get("devices", [])) + list(devices)
        if entrypoint is not None:
            kwargs["entrypoint"] = entrypoint
        if command is not None:
            kwargs["command"] = command
        if extra_docker_args:
            # Defense-in-depth: deny security-critical keys via extra_docker_args
            for k, v in extra_docker_args.items():
                if k in _EXTRA_DOCKER_ARGS_DENYLIST:
                    raise ValueError(f"extra_docker_args may not set '{k}'")
                if k == "labels":
                    kwargs.setdefault("labels", {}).update(v)
                else:
                    kwargs[k] = v

        try:
            self._client.images.get(image)
        except docker.errors.ImageNotFound:
            if "/" not in image:
                raise
            self._client.images.pull(image)

        # The name is deterministic + unique per instance (selkies-<subdomain>),
        # so a pre-existing container with this name is always a stale orphan of
        # this same instance (e.g. left by a crash before container_id was saved).
        # Remove it so launch/recreate is idempotent instead of 409-conflicting.
        try:
            self._client.containers.get(name).remove(force=True)
        except docker.errors.NotFound:
            pass

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

    def pull_image_streaming(self, image: str, on_progress=None) -> None:
        """Pull with layer-progress events. on_progress(percent:int, detail:str)."""
        # A colon is a tag separator only in the last path segment — otherwise
        # it's a registry port (e.g. registry:5000/img). Split accordingly.
        if ":" in image.rsplit("/", 1)[-1]:
            repo, tag = image.rsplit(":", 1)
        else:
            repo, tag = image, "latest"
        layers: dict[str, dict] = {}
        for ev in self._client.api.pull(repo, tag=tag or "latest", stream=True, decode=True):
            if ev.get("id"):
                layers[ev["id"]] = ev
            if on_progress:
                from app.services.pull_progress import overall_percent
                on_progress(overall_percent(list(layers.values())),
                            ev.get("status", "Pulling"))

    def ensure_user_network(self, user_id: str) -> str:
        """Per-user bridge network; traefik is attached so it can route to
        instance containers. Backend itself never joins user networks."""
        name = f"styx-u-{user_id[:12]}"
        try:
            net = self._client.networks.get(name)
        except docker.errors.NotFound:
            net = self._client.networks.create(name, driver="bridge")
        # Always (re)attach traefik, even when the network already existed —
        # traefik may have been recreated (new container, lost membership) since
        # the network was first made. Idempotent: a redundant connect raises
        # APIError, which we ignore.
        try:
            net.connect(TRAEFIK_CONTAINER)
        except docker.errors.APIError:
            pass  # already connected, or traefik not present (tests/dev)
        return name

    def remove_user_network(self, user_id: str) -> None:
        name = f"styx-u-{user_id[:12]}"
        try:
            net = self._client.networks.get(name)
        except docker.errors.NotFound:
            return
        try:
            net.disconnect(TRAEFIK_CONTAINER)
        except docker.errors.APIError:
            pass
        try:
            net.remove()
        except docker.errors.APIError:
            pass  # still has containers — leave it

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def version(self) -> str | None:
        try:
            return self._client.version().get("Version")
        except Exception:
            return None
