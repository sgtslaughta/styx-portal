from unittest.mock import AsyncMock

import pytest

from app.main import _capture_running_instances


class _Inst:
    def __init__(self, iid, status, cid):
        self.id = iid
        self.status = status
        self.container_id = cid


@pytest.mark.asyncio
async def test_captures_only_running_instances():
    svc = AsyncMock()

    targets = [
        (_Inst("a", "running", "c-a"), 3001),
        (_Inst("b", "idle", "c-b"), 443),
        (_Inst("c", "stopped", "c-c"), 3001),
        (_Inst("d", "running", None), 3001),
    ]

    await _capture_running_instances(svc, targets)

    captured = {call.args[0] for call in svc.capture.await_args_list}
    assert captured == {"a", "b"}
    # port is forwarded positionally from the tuple
    by_id = {call.args[0]: call.args[2] for call in svc.capture.await_args_list}
    assert by_id["b"] == 443
