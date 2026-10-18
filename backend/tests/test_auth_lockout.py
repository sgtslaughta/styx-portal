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
    assert r.status_code == 401          # locked looks exactly like a bad password
    assert r.json() == {"detail": "Invalid credentials"}
    assert "Retry-After" not in r.headers


async def test_lockout_blocks_correct_password(client, session):
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    # even the RIGHT password is refused while locked
    r = await client.post("/api/auth/login",
                          json={"username": "victim",
                                "password": "correct horse battery staple"})
    assert r.status_code == 401


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


async def test_lockout_expires_and_allows_login(client, session, monkeypatch):
    import time as _t
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login", json={"username": "victim", "password": "nope"})
    real = _t.monotonic
    monkeypatch.setattr("app.services.abuse.time.monotonic", lambda: real() + 901)
    r = await client.post("/api/auth/login",
                          json={"username": "victim",
                                "password": "correct horse battery staple"})
    assert r.status_code == 200, r.text


async def test_lockout_is_per_ip_not_global(client, session):
    # An attacker on one IP locks only their own (username, IP) pair.
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login", headers={"X-Forwarded-For": "6.6.6.6"},
                          json={"username": "victim", "password": "nope"})
    r = await client.post("/api/auth/login", headers={"X-Forwarded-For": "6.6.6.6"},
                          json={"username": "victim", "password": "correct horse battery staple"})
    assert r.status_code == 401
    r = await client.post("/api/auth/login", headers={"X-Forwarded-For": "8.8.4.4"},
                          json={"username": "victim", "password": "correct horse battery staple"})
    assert r.status_code == 200, r.text


async def test_unknown_and_locked_users_take_the_dummy_hash_path(client, session, monkeypatch):
    calls = []
    import app.routers.auth as auth_mod
    real = auth_mod.verify_password
    monkeypatch.setattr(auth_mod, "verify_password",
                        lambda pw, h: (calls.append(h), real(pw, h))[1])
    r = await client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401
    assert len(calls) == 1               # a hash is verified even for a missing user
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login", json={"username": "victim", "password": "nope"})
    calls.clear()
    await client.post("/api/auth/login", json={"username": "victim", "password": "nope"})
    assert len(calls) == 1               # and for a locked one


async def test_admin_unlock_clears_lockout(admin_client, session):
    from sqlmodel import select
    from app.models import User
    await _make_user(session)
    for _ in range(10):
        await admin_client.post("/api/auth/login", json={"username": "victim", "password": "nope"})
    victim = (await session.exec(select(User).where(User.username == "victim"))).first()
    r = await admin_client.post(f"/api/users/{victim.id}/unlock")
    assert r.status_code == 200, r.text
    r = await admin_client.post("/api/auth/login",
                                json={"username": "victim",
                                      "password": "correct horse battery staple"})
    assert r.status_code == 200, r.text


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
        assert r.status_code == 401
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


async def test_lockout_threshold_is_live(client, session):
    from app.services.settings_store import settings
    await settings.set(session, "LOCKOUT_THRESHOLD", 3, actor_id=None)
    await session.commit()
    await _make_user(session)
    for _ in range(3):
        r = await client.post("/api/auth/login",
                              json={"username": "victim", "password": "nope"})
        assert r.status_code == 401, r.text
    r = await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    assert r.status_code == 401


async def test_login_input_is_length_limited(client):
    r = await client.post("/api/auth/login", json={"username": "u", "password": "p" * 5000})
    assert r.status_code == 422
    r = await client.post("/api/auth/login", json={"username": "u" * 500, "password": "p"})
    assert r.status_code == 422


async def test_never_bans_a_trusted_proxy_address(client, session):
    from app.models import BannedIP
    # No usable forwarded header: the resolved "client" is the proxy peer itself.
    for i in range(20):
        await client.post("/api/auth/login", json={"username": f"nobody{i}", "password": "nope"})
    assert await session.get(BannedIP, "127.0.0.1") is None


async def test_distributed_guessing_is_throttled_but_never_hard_locked(client, session, monkeypatch):
    import time as _t
    await _make_user(session)
    for i in range(30):          # one failure each from 30 different IPs
        r = await client.post("/api/auth/login", headers={"X-Forwarded-For": f"203.0.113.{i + 1}"},
                              json={"username": "victim", "password": "nope"})
        assert r.status_code == 401
    good = {"username": "victim", "password": "correct horse battery staple"}
    h = {"X-Forwarded-For": "198.51.100.7"}
    # first check after the threshold is let through (and uses the 10 s slot) ...
    assert (await client.post("/api/auth/login", headers=h,
                              json={"username": "victim", "password": "nope"})).status_code == 401
    # ... so an immediate correct password is throttled with the same 401
    r = await client.post("/api/auth/login", headers=h, json=good)
    assert r.status_code == 401 and r.json() == {"detail": "Invalid credentials"}
    # the owner gets through once the slot reopens: throttled, never locked out
    real = _t.monotonic
    monkeypatch.setattr("app.services.abuse.time.monotonic", lambda: real() + 11)
    assert (await client.post("/api/auth/login", headers=h, json=good)).status_code == 200


async def test_unknown_username_locks_identically(client):
    from app.services.abuse import login_lockout
    for _ in range(10):
        r = await client.post("/api/auth/login", headers={"X-Forwarded-For": "5.5.5.5"},
                              json={"username": "ghost", "password": "nope"})
        assert r.status_code == 401
    assert login_lockout.is_locked("ghost", "5.5.5.5")


async def test_lockout_does_not_write_the_user_row(client, session):
    from sqlmodel import select
    from app.models import User
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login", json={"username": "victim", "password": "nope"})
    u = (await session.exec(select(User).where(User.username == "victim"))).first()
    assert u.locked_until is None


async def test_lan_client_is_banned_after_threshold(client, session):
    from app.models import BannedIP
    for i in range(20):
        await client.post("/api/auth/login", headers={"X-Forwarded-For": "192.168.5.5"},
                          json={"username": f"nobody{i}", "password": "nope"})
    assert await session.get(BannedIP, "192.168.5.5") is not None


async def test_raw_ipv6_ban_row_matches_client_in_the_64(client, session):
    from app.models import BannedIP
    from app.services.abuse import ban_cache
    from datetime import datetime, timedelta
    session.add(BannedIP(ip="2001:db8:1:2:aaaa:bbbb:cccc:dddd", reason="legacy",
                         expires_at=datetime.utcnow() + timedelta(hours=1)))
    await session.commit()
    ban_cache.invalidate()
    r = await client.get("/api/auth/ban-check",
                         headers={"X-Forwarded-For": "2001:db8:1:2:1111:2222:3333:4444"})
    assert r.status_code == 403


async def test_ipv4_mapped_client_matches_ipv4_ban(client, session):
    from app.services.abuse import ban_ip, ban_cache
    await ban_ip(session, "203.0.113.9", "t", 3600)
    await session.commit()
    ban_cache.invalidate()
    r = await client.get("/api/auth/ban-check", headers={"X-Forwarded-For": "::ffff:203.0.113.9"})
    assert r.status_code == 403
