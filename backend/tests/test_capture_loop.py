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
        (_Inst("a", "running", "c-a"), 3001, "https"),
        (_Inst("b", "idle", "c-b"), 3000, "http"),
        (_Inst("c", "stopped", "c-c"), 3001, "https"),
        (_Inst("d", "running", None), 3001, "https"),
    ]

    await _capture_running_instances(svc, targets)

    captured = {call.args[0] for call in svc.capture.await_args_list}
    assert captured == {"a", "b"}
    # port + protocol forwarded positionally from the tuple
    by_id = {call.args[0]: call.args[1:] for call in svc.capture.await_args_list}
    assert by_id["b"] == ("c-b", 3000, "http")
