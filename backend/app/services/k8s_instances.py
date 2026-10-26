"""Instance runtime on Kubernetes: same method names as DockerManager."""
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import Settings
from app.services.k8s_api import incluster_client
from app.services.k8s_instance_objects import build_objects, pvc

logger = logging.getLogger("styx-portal")
_APPS = "apps/v1"


class K8sUnsupported(HTTPException, NotImplementedError):
    """Operation with no k8s equivalent; surfaces as HTTP 422."""

    def __init__(self, msg: str):
        super().__init__(422, msg)


class K8sInstanceRuntime:
    def __init__(self, client=None):
        self._c = client or incluster_client()
        self._ns = Settings().K8S_INSTANCE_NAMESPACE

    # images: the kubelet pulls
    def image_exists(self, image: str) -> bool:
        return True

    def pull_image_streaming(self, image: str, on_progress=None) -> None:
        return None

    def get_image_info(self, image: str) -> dict | None:
        return {"size_mb": 0, "id": image}

    # volumes
    def create_volume(self, name: str) -> str:
        self._c.apply(pvc(name, self._ns))
        return name

    def remove_volume(self, name: str) -> None:
        self._c.delete("v1", "PersistentVolumeClaim", self._ns, name)

    def remove_image(self, image: str) -> None:
        return None

    # networks: policy is namespace-wide
    def ensure_user_network(self, user_id: str) -> str:
        return user_id

    def ensure_isolated(self, *a, **kw) -> None:
        return None

    def remove_user_network(self, *a, **kw) -> None:
        return None

    def on_portal_network(self, *a, **kw) -> list[str]:
        return []

    def create_container(self, name, image, labels, environment, volumes, port,
                         gpu_enabled=False, gpu_count=1, memory_limit=None,
                         cpu_limit=None, shm_size=None, privileged=False, dind=False,
                         cap_add=None, network=None, read_only_rootfs=False,
                         tmpfs=None, extra_hosts=None, entrypoint=None, command=None,
                         **ignored) -> str:
        if privileged or dind:
            raise ValueError("privileged/dind containers are not supported on Kubernetes")
        if ignored or labels:
            logger.info("k8s: ignoring container options %s", sorted(ignored))
        for obj in build_objects(
                name, image, environment, volumes, port, self._ns, network or "",
                gpu_enabled=gpu_enabled, gpu_count=gpu_count, memory_limit=memory_limit,
                cpu_limit=cpu_limit, shm_size=shm_size, cap_add=cap_add,
                read_only_rootfs=read_only_rootfs, tmpfs=tmpfs, extra_hosts=extra_hosts,
                entrypoint=entrypoint, command=command):
            self._c.apply(obj)
        return name

    def _patch(self, name: str, body: dict) -> None:
        self._c.patch_merge(_APPS, "Deployment", self._ns, name, body)

    def start_container(self, name: str) -> None:
        self._patch(name, {"spec": {"replicas": 1}})

    def stop_container(self, name: str) -> None:
        self._patch(name, {"spec": {"replicas": 0}})

    def restart_container(self, name: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._patch(name, {"spec": {"template": {"metadata": {
            "annotations": {"styx/restartedAt": now}}}}})

    def pause_container(self, name: str) -> None:
        raise K8sUnsupported("pause is not supported on Kubernetes")

    unpause_container = pause_container

    def remove_container(self, name: str) -> None:
        self._c.delete(_APPS, "Deployment", self._ns, name)
        self._c.delete("v1", "Service", self._ns, name)

    def _pods(self, name: str) -> list[dict]:
        data = self._c.get_json(f"/api/v1/namespaces/{self._ns}/pods",
                                {"labelSelector": f"app={name}"}) or {}
        return data.get("items", [])

    def get_container_status(self, name: str) -> dict:
        dep = self._c.get_json(
            f"/apis/apps/v1/namespaces/{self._ns}/deployments/{name}")
        if dep is None:
            return {"status": "not_found"}
        if (dep.get("spec") or {}).get("replicas", 0) == 0:
            return {"status": "exited"}
        if ((dep.get("status") or {}).get("readyReplicas") or 0) >= 1:
            pods = self._pods(name)
            started = (pods[0].get("status") or {}).get("startTime", "") if pods else ""
            return {"status": "running", "started_at": started}
        return {"status": "created"}

    def get_container_stats(self, name: str) -> dict:
        return {}

    def instance_logs(self, name: str, tail: int = 200) -> list[str]:
        pods = self._pods(name)
        if not pods:
            return []
        text = self._c.get_text(
            f"/api/v1/namespaces/{self._ns}/pods/{pods[0]['metadata']['name']}/log",
            {"tailLines": tail, "timestamps": "true"})
        return text.splitlines() if text else []
