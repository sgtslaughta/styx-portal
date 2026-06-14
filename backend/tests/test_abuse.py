from datetime import datetime, timezone, timedelta

from app.services.abuse import IpFailTracker, BanCache, ban_ip
from app.models import BannedIP


def test_fail_tracker_fires_at_threshold():
    t = IpFailTracker(threshold=3, window=600)
    assert t.record("ip1", now=0) is False
    assert t.record("ip1", now=1) is False
    assert t.record("ip1", now=2) is True   # 3rd fail crosses


def test_fail_tracker_clears_after_fire():
    t = IpFailTracker(threshold=2, window=600)
    assert t.record("ip1", now=0) is False
    assert t.record("ip1", now=1) is True
    # window cleared on fire -> next fail starts fresh, does not re-fire immediately
    assert t.record("ip1", now=2) is False


def test_fail_tracker_window_slides():
    t = IpFailTracker(threshold=2, window=60)
    assert t.record("ip1", now=0) is False
    assert t.record("ip1", now=61) is False  # first hit aged out


def test_fail_tracker_keys_isolated():
    t = IpFailTracker(threshold=2, window=60)
    assert t.record("ip1", now=0) is False
    assert t.record("ip2", now=0) is False


async def test_ban_ip_inserts_and_updates(session):
    now = datetime.now(timezone.utc)
    await ban_ip(session, "203.0.113.5", "brute-force", 3600, now=now)
    await session.commit()
    row = await session.get(BannedIP, "203.0.113.5")
    # SQLite stores as naive; compare naive datetime
    expected = (now + timedelta(seconds=3600)).replace(tzinfo=None)
    actual = row.expires_at.replace(tzinfo=None) if row.expires_at.tzinfo else row.expires_at
    assert actual == expected
    # second ban updates the same row, not a duplicate
    later = now + timedelta(seconds=10)
    await ban_ip(session, "203.0.113.5", "again", 60, now=later)
    await session.commit()
    row2 = await session.get(BannedIP, "203.0.113.5")
    assert row2.reason == "again"
    expected2 = (later + timedelta(seconds=60)).replace(tzinfo=None)
    actual2 = row2.expires_at.replace(tzinfo=None) if row2.expires_at.tzinfo else row2.expires_at
    assert actual2 == expected2


async def test_ban_cache_reports_active_and_expired(session):
    now = datetime.now(timezone.utc)
    await ban_ip(session, "198.51.100.2", "x", 3600, now=now)
    await session.commit()
    cache = BanCache(ttl=30)
    # active ban
    assert await cache.is_banned(session, "198.51.100.2", now=now, mono=0.0) is True
    # unrelated IP
    assert await cache.is_banned(session, "10.0.0.1", now=now, mono=0.0) is False
    # after expiry, a refresh drops the row -> no longer banned
    future = now + timedelta(hours=2)
    cache.invalidate()
    assert await cache.is_banned(session, "198.51.100.2", now=future, mono=100.0) is False


async def test_ban_cache_invalidate_forces_refresh(session):
    now = datetime.now(timezone.utc)
    cache = BanCache(ttl=9999)
    assert await cache.is_banned(session, "192.0.2.1", now=now, mono=0.0) is False
    await ban_ip(session, "192.0.2.1", "x", 3600, now=now)
    await session.commit()
    # without invalidate the long TTL would hide the new ban
    cache.invalidate()
    assert await cache.is_banned(session, "192.0.2.1", now=now, mono=1.0) is True
