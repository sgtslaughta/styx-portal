from unittest.mock import MagicMock

from app.models import Instance, ServiceTemplate
from app.routers.instances import _build_and_start_container


async def test_ownerless_instance_never_uses_portal_network():
    docker = MagicMock()
    docker.ensure_user_network.return_value = "styx-u-ownerless"
    docker.create_container.return_value = "cid"
    inst = Instance(template_id="t", owner_id=None, name="n", subdomain="n")
    tmpl = ServiceTemplate(name="t", display_name="t", image="x")
    await _build_and_start_container(inst, tmpl, docker)
    docker.ensure_user_network.assert_called_once_with("ownerless")
    assert docker.create_container.call_args.kwargs["network"] == "styx-u-ownerless"
