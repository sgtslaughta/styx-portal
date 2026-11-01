from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from app.models import MetricHour
from app.services import host_metrics, metric_rollup
from app.services.metrics_store import get_history

H = datetime(2026, 10, 1, 10)


@pytest.fixture(autouse=True)
def _reset():
    metric_rollup.reset()


async def test_rollup_avg_and_max(session):
    for i in range(120):
        metric_rollup.record_host(10 if i % 2 else 30, 50, 40, i % 4, ts=H + timedelta(seconds=30 * i))
    assert await metric_rollup.rollup(session, now=H + timedelta(hours=1)) == 1
    rows = (await session.exec(select(MetricHour))).all()
    assert len(rows) == 1
    r = rows[0]
    assert (r.cpu_avg, r.cpu_max, r.ram_avg, r.disk_pct, r.live_max) == (20, 30, 50, 40, 3)


async def test_current_hour_not_flushed_unless_forced(session):
    metric_rollup.record_host(10, 10, ts=H)
    assert await metric_rollup.rollup(session, now=H + timedelta(minutes=5)) == 0
    assert metric_rollup.current_hour_values(H + timedelta(minutes=5))["cpu_avg"] == 10
    assert await metric_rollup.rollup(session, now=H + timedelta(minutes=5), force=True) == 1


async def test_prunes_older_than_90_days(session):
    now = datetime(2026, 10, 1, 12)
    session.add(MetricHour(ts_hour=now - timedelta(days=91)))
    session.add(MetricHour(ts_hour=now - timedelta(days=89)))
    await session.commit()
    await metric_rollup.rollup(session, now=now)
    rows = (await session.exec(select(MetricHour))).all()
    assert [r.ts_hour for r in rows] == [now - timedelta(days=89)]


async def test_history_7d_reads_hour_rows(session):
    session.add(MetricHour(ts_hour=H, cpu_avg=5, ram_avg=7))
    await session.commit()
    rows = await metric_rollup.hour_rows(session, 7, now=H + timedelta(days=1))
    h = get_history("7d", rows)
    assert h["aggregate_cpu"] == [5] and h["aggregate_ram"] == [7] and len(h["timestamps"]) == 1


def test_host_metrics_proc(tmp_path, monkeypatch):
    real = open
    stat = tmp_path / "stat"
    mem = tmp_path / "meminfo"
    mem.write_text("MemTotal: 2048000 kB\nMemFree: 1 kB\nMemAvailable: 1024000 kB\n")
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: real(
        {"/proc/stat": stat, "/proc/meminfo": mem}.get(p, p), *a, **k))
    host_metrics._last = None
    stat.write_text("cpu 100 0 100 800 0 0 0 0 0 0\n")
    assert host_metrics.cpu_pct() is None
    stat.write_text("cpu 200 0 200 900 0 0 0 0 0 0\n")   # +200 busy, +100 idle
    assert host_metrics.cpu_pct() == pytest.approx(66.7)
    assert host_metrics.ram() == (50.0, 2000)


def test_host_metrics_no_proc(monkeypatch):
    def boom(*a, **k):
        raise OSError
    monkeypatch.setattr("builtins.open", boom)
    assert host_metrics.cpu_pct() is None and host_metrics.ram() is None


async def test_ram_only_bucket_has_null_cpu(session):
    metric_rollup.record_host(None, 40, ts=H)
    await metric_rollup.rollup(session, now=H + timedelta(hours=1))
    r = (await session.exec(select(MetricHour))).one()
    assert r.cpu_avg is None and r.cpu_max is None and r.ram_avg == 40
