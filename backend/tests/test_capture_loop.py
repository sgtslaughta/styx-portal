from unittest.mock import AsyncMock

import pytest

from app.main import _capture_running_instances


@pytest.mark.asyncio
async def test_captures_only_running_instances():
    svc = AsyncMock()

    class Inst:
        def __init__(self, iid, status, cid, port=3001):
            self.id = iid
            self.status = status
            self.container_id = cid
            self.port = port

    instances = [
        Inst("a", "running", "c-a"),
        Inst("b", "idle", "c-b"),
        Inst("c", "stopped", "c-c"),
        Inst("d", "running", None),
    ]

    await _capture_running_instances(svc, instances)

    captured = {call.args[0] for call in svc.capture.await_args_list}
    assert captured == {"a", "b"}
