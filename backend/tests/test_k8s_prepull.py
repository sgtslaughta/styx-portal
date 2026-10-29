from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import ServiceTemplate
from app.services import k8s_prepull as pp


def test_daemonset_shape():
    ds = pp.build_prepull_daemonset(["a/x:latest", "b/y:latest"], "ns", stamp="T")
    assert ds["metadata"] == {"name": "styx-image-prepull", "namespace": "ns",
                              "labels": {"app.kubernetes.io/managed-by": "styx-backend"}}
    tpl = ds["spec"]["template"]
    assert tpl["metadata"]["annotations"] == {"styx/prepull-at": "T"}
    pod = tpl["spec"]
    assert pod["tolerations"] == [{"operator": "Exists"}]
    assert pod["automountServiceAccountToken"] is False and pod["enableServiceLinks"] is False
    assert pod["securityContext"] == {"seccompProfile": {"type": "RuntimeDefault"}}
    inits = pod["initContainers"]
    assert [c["name"] for c in inits] == ["img-0", "img-1"]
    assert [c["image"] for c in inits] == ["a/x:latest", "b/y:latest"]
    for c in inits:
        assert c["imagePullPolicy"] == "Always" and c["command"] == ["sh", "-c", "exit 0"]
        assert c["securityContext"]["allowPrivilegeEscalation"] is False
        assert c["securityContext"]["capabilities"] == {"drop": ["ALL"]}
        assert c["resources"]["requests"] == {"cpu": "1m", "memory": "8Mi"}
    assert pod["containers"][0]["image"] == "registry.k8s.io/pause:3.10"


def test_images_distinct_mapped_and_filtered(monkeypatch):
    monkeypatch.setenv("K8S_DESKTOP_IMAGE", "reg/desktop:latest")
    T = lambda image, **kw: SimpleNamespace(image=image, dind=False, privileged=False, cap_add=[], **kw)  # noqa: E731
    ts = [T("a/x:1"), T("a/x:1"), T("local-name"), T("b/y:1", ), SimpleNamespace(
        image="bad/z:1", dind=True, privileged=False, cap_add=[])]
    assert pp.prepull_images(ts) == ["a/x:1", "reg/desktop:latest", "b/y:1"]


@pytest.mark.asyncio
async def test_sync_skipped_on_docker(session, monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "file")
    with patch("app.services.k8s_api.incluster_client") as c:
        await pp.sync_prepull(session)
    c.assert_not_called()


@pytest.mark.asyncio
async def test_sync_applies_on_k8s(session, monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    session.add(ServiceTemplate(name="t", display_name="T", image="a/x:1", internal_port=3000))
    await session.commit()
    with patch("app.services.k8s_api.incluster_client") as c:
        await pp.sync_prepull(session)
    ds = c.return_value.apply.call_args[0][0]
    assert ds["kind"] == "DaemonSet"
    assert [i["image"] for i in ds["spec"]["template"]["spec"]["initContainers"]] == ["a/x:1"]


def test_schedule_noop_on_docker(monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "file")
    with patch("asyncio.create_task") as ct:
        pp.schedule_sync()
    ct.assert_not_called()
