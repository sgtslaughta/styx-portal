async def _make_user(session, name="victim", pw="correct horse battery staple"):
    from app.models import User
    from app.security.passwords import hash_password
    session.add(User(username=name, password_hash=hash_password(pw),
                     role="member", is_active=True))
    await session.commit()


async def test_lockout_after_threshold(client, session):
    await _make_user(session)
    # 10 wrong attempts -> 401 each; 11th is locked even with the WRONG password
    for _ in range(10):
        r = await client.post("/api/auth/login",
                              json={"username": "victim", "password": "nope"})
        assert r.status_code == 401, r.text
    r = await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    assert r.status_code == 423
    assert r.headers.get("Retry-After")


async def test_lockout_blocks_correct_password(client, session):
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    # even the RIGHT password is refused while locked
    r = await client.post("/api/auth/login",
                          json={"username": "victim",
                                "password": "correct horse battery staple"})
    assert r.status_code == 423


async def test_success_resets_failed_count(client, session):
    from app.models import User
    from sqlmodel import select
    await _make_user(session)
    for _ in range(3):
        await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    r = await client.post("/api/auth/login",
                          json={"username": "victim",
                                "password": "correct horse battery staple"})
    assert r.status_code == 200
    u = (await session.exec(select(User).where(User.username == "victim"))).first()
    assert u.failed_count == 0
    assert u.locked_until is None


async def test_lockout_expires_and_allows_login(client, session):
    from datetime import datetime, timezone, timedelta
    from app.models import User
    from sqlmodel import select
    await _make_user(session)
    # Lock the account, but with an already-past expiry.
    u = (await session.exec(select(User).where(User.username == "victim"))).first()
    u.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.add(u)
    await session.commit()
    # Expired lock must NOT return 423; correct password logs in.
    r = await client.post("/api/auth/login",
                          json={"username": "victim",
                                "password": "correct horse battery staple"})
    assert r.status_code == 200, r.text


async def test_retry_after_within_lockout_duration(client, session):
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    r = await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    assert r.status_code == 423
    retry = int(r.headers["Retry-After"])
    assert 0 < retry <= 900   # within LOCKOUT_DURATION (15 min)


async def test_locked_user_does_not_feed_ip_tracker(client, session):
    # Once a username is locked (423 path), further attempts must NOT increment
    # the per-IP fail tracker (the lock already punishes the attacker).
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login",
                          headers={"X-Forwarded-For": "7.7.7.7"},
                          json={"username": "victim", "password": "nope"})
    # IP has recorded 10 fails so far; record() count is internal. Hammer the
    # now-locked account 30 more times — all hit the 423 path.
    for _ in range(30):
        r = await client.post("/api/auth/login",
                              headers={"X-Forwarded-For": "7.7.7.7"},
                              json={"username": "victim", "password": "nope"})
        assert r.status_code == 423
    # The 30 locked attempts did not feed the tracker: the IP's recorded-fail
    # deque still holds only the original 10 (< BAN_FAIL_THRESHOLD 20), so no
    # ban row was written for this IP.
    from app.models import BannedIP
    assert await session.get(BannedIP, "7.7.7.7") is None


async def test_ban_check_allows_unbanned(client):
    r = await client.get("/api/auth/ban-check")
    assert r.status_code == 200


async def test_ban_check_blocks_banned_ip(client, session):
    from app.services.abuse import ban_ip, ban_cache
    await ban_ip(session, "1.2.3.4", "test", 3600)
    await session.commit()
    ban_cache.invalidate()
    # client IP arrives via X-Forwarded-For (trusted behind the proxy)
    r = await client.get("/api/auth/ban-check",
                         headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 403
    # a different IP is still allowed
    r2 = await client.get("/api/auth/ban-check",
                          headers={"X-Forwarded-For": "5.6.7.8"})
    assert r2.status_code == 200


async def test_brute_force_bans_ip_after_threshold(client, session):
    from app.models import BannedIP
    # 20 failed logins from one IP using UNKNOWN usernames -> every attempt takes
    # the 401 path (unknown users never lock), so all 20 are recorded against the
    # IP and the abuse detector writes a ban row at the threshold.
    for i in range(20):
        await client.post("/api/auth/login",
                          headers={"X-Forwarded-For": "9.9.9.9"},
                          json={"username": f"nobody{i}", "password": "nope"})
    row = await session.get(BannedIP, "9.9.9.9")
    assert row is not None
