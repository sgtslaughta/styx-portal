from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import ServiceTemplate
from app.services import k8s_prepull as pp


def test_daemonset_shape():
    ds = pp.build_prepull_daemonset("a/x:latest", "ns", stamp="T")
    name = pp.prepull_name("a/x:latest")
    assert name.startswith("styx-prepull-") and len(name) == len("styx-prepull-") + 10
    assert name != pp.prepull_name("b/y:latest")
    assert ds["metadata"]["name"] == name
    assert ds["metadata"]["labels"] == {"styx/prepull": "true",
                                        "app.kubernetes.io/managed-by": "styx-backend"}
    tpl = ds["spec"]["template"]
    assert tpl["metadata"]["annotations"] == {"styx/prepull-at": "T"}
    pod = tpl["spec"]
    assert "tolerations" not in pod
    assert pod["automountServiceAccountToken"] is False and pod["enableServiceLinks"] is False
    assert pod["securityContext"] == {"seccompProfile": {"type": "RuntimeDefault"}}
    (init,) = pod["initContainers"]
    assert init["image"] == "a/x:latest" and init["imagePullPolicy"] == "Always"
    assert init["command"] == ["sh", "-c", "exit 0"]
    for c in (init, pod["containers"][0]):
        sc = c["securityContext"]
        assert sc["runAsNonRoot"] is True and sc["runAsUser"] == 65534 == sc["runAsGroup"]
        assert sc["allowPrivilegeEscalation"] is False and sc["readOnlyRootFilesystem"] is True
        assert sc["capabilities"] == {"drop": ["ALL"]}
        assert c["resources"]["requests"] == c["resources"]["limits"] == {"cpu": "10m", "memory": "16Mi"}
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
async def test_sync_trusted_only_one_ds_per_image_and_prunes(session, monkeypatch):
    from app.models import User
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    admin = User(username="adm", password_hash="x", role="admin")
    member = User(username="mem", password_hash="x", role="user")
    session.add_all([admin, member])
    await session.commit()
    for n, img, owner in [("s", "shared/x:1", None), ("a", "admin/y:1", admin.id),
                          ("m", "member/z:1", member.id)]:
        session.add(ServiceTemplate(name=n, display_name=n, image=img, internal_port=3000,
                                    owner_id=owner))
    await session.commit()
    with patch("app.services.k8s_api.incluster_client") as c:
        cl = c.return_value
        cl.list_names.return_value = [pp.prepull_name("shared/x:1"), "styx-prepull-stale"]
        await pp.sync_prepull(session)
    applied = {call[0][0]["metadata"]["name"]: call[0][0] for call in cl.apply.call_args_list}
    assert set(applied) == {pp.prepull_name("shared/x:1"), pp.prepull_name("admin/y:1")}
    cl.delete.assert_called_once_with("apps/v1", "DaemonSet", "styx-instances", "styx-prepull-stale")


def test_schedule_noop_on_docker(monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "file")
    with patch("asyncio.create_task") as ct:
        pp.schedule_sync()
    ct.assert_not_called()
