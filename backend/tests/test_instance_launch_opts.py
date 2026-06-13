"""Test that new template fields are forwarded to docker.create_container at launch."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.routers.instances import _launch_instance_background
from app.models import Instance


TEMPLATE_WITH_OPTS = {
    "name": "opts-tmpl",
    "display_name": "Template With Options",
    "image": "test:latest",
    "internal_port": 3001,
    "env_vars": {"PUID": "1000"},
    "volumes": [{"name": "{instance_id}-home", "mount": "/config"}],
    "restart_policy": "unless-stopped",
    "read_only_rootfs": True,
    "tmpfs": ["/tmp", "/run"],
    "extra_hosts": {"localhost": "127.0.0.1"},
    "ulimits": [{"name": "nofile", "soft": 1024, "hard": 2048}],
    "devices": ["/dev/dri:/dev/dri"],
    "entrypoint": ["/bin/sh"],
    "command": ["-c", "echo hello"],
    "privileged": False,
    "extra_docker_args": {"hostname": "box"},
    "session_config": {
        "idle_timeout": "30m",
        "grace_period": "5m",
        "timeout_action": "stop",
        "never_timeout": False,
        "max_session_duration": None,
    },
}


@pytest.fixture
async def opts_template_id(admin_client):
    resp = await admin_client.post("/api/templates", json=TEMPLATE_WITH_OPTS)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_launch_forwards_new_template_opts(session, opts_template_id):
    """Direct test: call _launch_instance_background and verify create_container
    receives the template's new fields."""
    from app.models import User
    from app.security.passwords import hash_password

    # Create an admin user if not exists
    from sqlmodel import select
    admin = (await session.exec(
        select(User).where(User.username == "admin")
    )).first()
    if not admin:
        admin = User(
            username="admin",
            password_hash=hash_password("test"),
            role="admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()

    # Create an instance manually in the DB
    instance = Instance(
        template_id=opts_template_id,
        owner_id=admin.id,
        name="opts-inst",
        subdomain="opts-inst",
        status="starting",
        volume_names=[],
    )
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    instance_id = instance.id

    # Mock docker manager
    manager = MagicMock()
    manager.create_volume.side_effect = lambda name: name
    manager.create_container.return_value = "container-abc123"
    manager.image_exists.return_value = True
    manager.pull_image_streaming = AsyncMock()
    manager.start_container = MagicMock()
    manager.get_image_info.return_value = {"size_mb": 100}

    # Patch get_docker_manager for the background task
    with patch("app.routers.instances.DockerManager") as mock_dm_class:
        mock_dm_class.return_value = manager
        # Also patch async_session to use our test session
        class AsyncSessionContextManager:
            async def __aenter__(self):
                return session
            async def __aexit__(self, *args):
                pass

        def mock_async_session_factory():
            return AsyncSessionContextManager()

        with patch("app.routers.instances.async_session", mock_async_session_factory):
            # Run the background task
            await _launch_instance_background(instance_id, opts_template_id)

    # Verify create_container was called with new fields
    manager.create_container.assert_called_once()
    call_kwargs = manager.create_container.call_args.kwargs

    assert call_kwargs["restart_policy"] == "unless-stopped"
    assert call_kwargs["read_only_rootfs"] is True
    assert call_kwargs["tmpfs"] == ["/tmp", "/run"]
    assert call_kwargs["extra_hosts"] == {"localhost": "127.0.0.1"}
    assert call_kwargs["ulimits"] == [{"name": "nofile", "soft": 1024, "hard": 2048}]
    assert call_kwargs["devices"] == ["/dev/dri:/dev/dri"]
    assert call_kwargs["entrypoint"] == ["/bin/sh"]
    assert call_kwargs["command"] == ["-c", "echo hello"]
    assert call_kwargs["privileged"] is False
    assert call_kwargs["extra_docker_args"] == {"hostname": "box"}
