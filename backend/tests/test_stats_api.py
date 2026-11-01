import pytest

from app.models import StreamSession
from app.services import cf_turn_usage, metric_rollup


@pytest.mark.parametrize("path", ["overview", "streaming", "relay"])
async def test_non_admin_403(member_client, path):
    assert (await member_client.get(f"/api/admin/stats/{path}")).status_code == 403


async def test_overview_shape(admin_client):
    metric_rollup.reset()
    metric_rollup.record_host(12.0, 34.0, 50.0, 1)
    r = await admin_client.get("/api/admin/stats/overview?range=7d")
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j["tiles"]) == {"cpu", "ram", "disk", "live"}
    assert all(len(t["series"]) == 24 for t in j["tiles"].values())
    assert j["tiles"]["cpu"]["series"][-1] == 12.0
    assert len(j["health_hours"]) == 24 and set(j["health_hours"]) <= {"ok", "warn", "fail"}
    assert len(j["sessions_per_day"]) == 14 and set(j["load"]) == {"labels", "cpu", "ram"}


async def test_streaming_rows(admin_client, session):
    session.add(StreamSession(target_kind="workstation", target_id="gone", user_id=None))
    await session.commit()
    r = await admin_client.get("/api/admin/stats/streaming?days=7&top=5")
    assert r.status_code == 200 and len(r.json()["rows"]) == 1


async def test_relay_404_when_unconfigured(admin_client, monkeypatch):
    monkeypatch.setattr(cf_turn_usage, "configured", lambda: False)
    assert (await admin_client.get("/api/admin/stats/relay")).status_code == 404


@pytest.mark.parametrize("period", ["this", "last", "6m"])
async def test_relay_shape(admin_client, monkeypatch, period):
    monkeypatch.setattr(cf_turn_usage, "configured", lambda: True)

    async def egress(now=None, client=None):
        return {"bytes": None, "error": None}
    monkeypatch.setattr(cf_turn_usage, "month_egress", egress)
    r = await admin_client.get(f"/api/admin/stats/relay?period={period}")
    assert r.status_code == 200, r.text
    j = r.json()
    assert len(j["daily"]) == 30 and len(j["monthly"]) == 6
    assert {"used_gb", "free_gb", "projected_gb", "est_usd", "budget_usd", "relayed_pct",
            "by_user", "by_workstation", "reasons"} <= set(j)


async def test_system_metrics_host_fields(admin_client):
    j = (await admin_client.get("/api/system/metrics")).json()
    assert {"host_cpu_pct", "host_ram_pct", "host_ram_total_mb"} <= set(j)
