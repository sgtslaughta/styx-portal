import io
import logging
import os
import posixpath
import re
import tarfile
import time
from pathlib import Path

import docker
import docker.errors
from docker.types import DeviceRequest, Ulimit

from app.config import Settings

logger = logging.getLogger("styx-portal")

# Defense-in-depth: denylist of security-critical keys that extra_docker_args
# must never set, even if validation bypasses. These are enforced at the sink.
_EXTRA_DOCKER_ARGS_DENYLIST = {
    "privileged", "cap_add", "cap_drop", "security_opt", "devices",
    "device_requests", "network_mode", "network", "pid_mode",
    "ipc_mode", "userns_mode", "uts_mode", "binds", "volumes",
    "mounts", "volumes_from", "cgroup_parent", "sysctls",
    "restart_policy", "runtime", "device_cgroup_rules",
}


# Untrusted (container-sourced) archive streams: a single file is capped at
# 1 MiB; the raw tar stream (headers + padding) at 2 MiB.
_FILE_CAP = 1024 * 1024
_STREAM_CAP = 2 * 1024 * 1024


def _join_capped(stream) -> bytes:
    buf = io.BytesIO()
    for chunk in stream:
        buf.write(chunk)
        if buf.tell() > _STREAM_CAP:
            raise ValueError("archive stream exceeds 2 MiB cap")
    return buf.getvalue()


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


_PROBE_URL = re.compile(r"https?://[A-Za-z0-9._:/@%+=~-]+")


class DockerManager:
    def __init__(self, network_name: str = "styx-portal", base_url: str | None = None):
        # Lazy connect: do NOT open the socket here. Eager construction raises if
        # the docker socket is absent (CI runners, docker-down hosts), which would
        # 500 diagnostics + setup-preflight — the very endpoints meant to *report*
        # docker being down. The client is built on first use; ping()/version()
        # already degrade gracefully, so the failure surfaces there as a clean
        # "not reachable", not an exception.
        cfg = Settings()
        self._url = base_url or cfg.DOCKER_SOCKET
        self._traefik = cfg.TRAEFIK_CONTAINER
        self._project = cfg.COMPOSE_PROJECT
        self._client_obj: docker.DockerClient | None = None
        self._network_name = network_name

    @property
    def _client(self) -> docker.DockerClient:
        if self._client_obj is None:
            self._client_obj = docker.DockerClient(base_url=self._url)
        return self._client_obj

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
        container.restart(timeout=30)

    def remove_container(self, container_id: str) -> None:
        container = self._client.containers.get(container_id)
        container.remove(force=True)

    def read_file(self, container: str, path: str) -> tuple[bytes, tarfile.TarInfo] | None:
        """(bytes, TarInfo) of one regular file inside a container, or None.

        None when the path is missing, is not a single regular-file member
        (symlink, hardlink, dir, ...), or the archive is empty. Raises
        ValueError when the stream or the file exceeds the size caps.
        """
        try:
            stream, _ = self._client.containers.get(container).get_archive(path)
        except docker.errors.NotFound:
            return None
        raw = _join_capped(stream)
        try:
            tf = tarfile.open(fileobj=io.BytesIO(raw))
        except tarfile.TarError as e:
            raise ValueError(f"malformed archive for {path}") from e
        members = tf.getmembers()
        if len(members) != 1 or not members[0].isreg():
            return None
        info = members[0]
        if info.size > _FILE_CAP:
            raise ValueError(f"{path} exceeds 1 MiB cap")
        return tf.extractfile(info).read(), info

    def write_file(self, container: str, path: str, data: bytes, like: tarfile.TarInfo) -> None:
        """Replace one file, keeping the original mode/uid/gid of `like`."""
        info = tarfile.TarInfo(posixpath.basename(path))
        info.size = len(data)
        info.mode = like.mode
        info.uid = like.uid
        info.gid = like.gid
        info.mtime = int(time.time())
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            tf.addfile(info, io.BytesIO(data))
        self._client.containers.get(container).put_archive(
            posixpath.dirname(path), buf.getvalue())

    def probe_http(self, url: str, network: str, timeout_s: int = 5,
                   extra_hosts: dict | None = None) -> int:
        """HTTP status of `url` fetched from a throwaway container on `network`; 0 on failure."""
        if not _PROBE_URL.fullmatch(url):
            raise ValueError("probe url must be plain http(s) with no shell metacharacters")
        image = Settings().MOUNT_PROBE_IMAGE
        c = None
        try:
            try:
                self._client.images.get(image)
            except docker.errors.ImageNotFound:
                self._client.images.pull(image)
            c = self._client.containers.create(
                image, ["wget", "-q", "-S", "-O", "/dev/null", "-T", str(timeout_s), url],
                network=network, read_only=True, cap_drop=["ALL"], mem_limit="32m", pids_limit=32,
                security_opt=["no-new-privileges"], labels={"styx.probe": "true"},
                extra_hosts=extra_hosts)
            c.start()
        except Exception as e:  # noqa: BLE001 - the probe itself could not run
            logger.warning("Couldn't run the probe image %s: %s", image, e)
            self._rm_probe(c)
            return -1
        try:
            c.wait(timeout=timeout_s + 10)
            out = c.logs(stdout=True, stderr=True).decode("utf-8", "replace")
            # busybox wget follows redirects and prints every hop; the first
            # status line is the app's own answer (3xx counts as up).
            codes = re.findall(r"HTTP/1\.[01] (\d{3})", out)
            return int(codes[0]) if codes else 0
        except Exception:  # noqa: BLE001 - unreachable app == status 0
            logger.debug("probe of %s failed", url, exc_info=True)
            return 0
        finally:
            self._rm_probe(c)

    @staticmethod
    def _rm_probe(c) -> None:
        if c is not None:
            try:
                c.remove(force=True)
            except Exception:  # noqa: BLE001
                logger.warning("could not remove probe container", exc_info=True)

    def remove_probe_containers(self) -> int:
        """Force-remove probe containers left behind by a crash."""
        n = 0
        for c in self._client.containers.list(all=True, filters={"label": "styx.probe=true"}):
            self._rm_probe(c)
            n += 1
        return n

    def container_labels(self, container: str) -> dict:
        return self._client.containers.get(container).labels or {}

    def container_logs(self, container: str, tail: int = 20) -> str:
        raw = self._client.containers.get(container).logs(tail=tail)
        return raw.decode("utf-8", "replace")

    def get_container_status(self, container_id: str) -> dict:
        try:
            container = self._client.containers.get(container_id)
            return {
                "status": container.status,
                "started_at": container.attrs["State"]["StartedAt"],
            }
        except docker.errors.NotFound:
            return {"status": "not_found"}

    def container_health(self, name: str) -> str:
        """healthy | unhealthy | unknown for a proxied docker-local service.

        Not running or missing = unhealthy. A Docker HEALTHCHECK, if defined,
        decides for a running container ("starting" = unknown). Docker API
        errors = unknown (we can't tell, so don't claim the app is down).
        """
        try:
            c = self._client.containers.get(name)
        except docker.errors.NotFound:
            return "unhealthy"
        except docker.errors.DockerException:
            return "unknown"
        if c.status != "running":
            return "unhealthy"
        hc = (c.attrs.get("State") or {}).get("Health")
        if not hc:
            return "healthy"
        return {"healthy": "healthy", "unhealthy": "unhealthy"}.get(hc.get("Status"), "unknown")

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
        return self.ensure_traefik_network(f"styx-u-{user_id[:12]}")

    def ensure_traefik_network(self, name: str) -> str:
        """Bridge network `name` (created if missing) with traefik attached."""
        try:
            net = self._client.networks.get(name)
        except docker.errors.NotFound:
            net = self._client.networks.create(name, driver="bridge")
        # Always (re)attach traefik, even when the network already existed —
        # traefik may have been recreated (new container, lost membership) since
        # the network was first made. Idempotent: a redundant connect raises
        # APIError, which we ignore.
        try:
            net.connect(self._traefik)
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
            net.disconnect(self._traefik)
        except docker.errors.APIError:
            pass
        try:
            net.remove()
        except docker.errors.APIError:
            pass  # still has containers — leave it

    def connect_to_network(self, container: str, network: str | None = None) -> bool:
        """Attach a container to the styx network so Traefik can reach it. False on failure."""
        try:
            net = self._client.networks.get(network or self._network_name)
            net.connect(container)
            return True
        except docker.errors.NotFound:
            return False
        except docker.errors.APIError as e:
            if "already exists" in str(e).lower():
                return True
            logger.warning("network connect failed for %s: %s", container, e)
            return False

    def disconnect_from_network(self, container: str, network: str | None = None) -> None:
        try:
            self._client.networks.get(network or self._network_name).disconnect(container)
        except docker.errors.DockerException:
            pass

    def list_containers(self) -> list[dict]:
        """Running containers not managed by Styx and not part of the Styx compose stack."""
        own_project = self._project or None
        if own_project is None:
            try:
                own_project = self._client.containers.get(self._traefik).labels.get(
                    "com.docker.compose.project")
            except docker.errors.DockerException:
                pass
        out = []
        for c in self._client.containers.list():
            labels = c.labels or {}
            if labels.get("styx-portal.managed") == "true":
                continue
            if own_project and labels.get("com.docker.compose.project") == own_project:
                continue
            ports = sorted({int(p.split("/")[0]) for p in
                            (c.attrs.get("Config", {}).get("ExposedPorts") or {})})
            nets = list((c.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())
            image = c.image.tags[0] if c.image.tags else str(c.image.id)
            out.append({"name": c.name, "image": image, "ports": ports, "networks": nets})
        return out

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
