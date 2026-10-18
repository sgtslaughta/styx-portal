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


async def test_unresolved_client_is_not_banned_and_logs_error(client, session, caplog):
    import logging
    from app.models import BannedIP
    # Peer is the proxy and there are no forwarded headers: the real client is unknown.
    with caplog.at_level(logging.ERROR, logger="styx-portal"):
        for i in range(20):
            await client.post("/api/auth/login", json={"username": f"nobody{i}", "password": "nope"})
    assert await session.get(BannedIP, "127.0.0.1") is None
    assert any("client IP not resolved" in m for m in caplog.messages)


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


async def test_unknown_username_is_indistinguishable_and_untracked(client, session):
    from app.services.abuse import login_lockout
    await _make_user(session)
    out = {}
    for name in ("ghost", "victim"):
        for _ in range(11):
            r = await client.post("/api/auth/login", headers={"X-Forwarded-For": "5.5.5.5"},
                                  json={"username": name, "password": "nope"})
        out[name] = (r.status_code, r.json(), dict(r.headers).get("retry-after"))
    assert out["ghost"] == out["victim"] == (401, {"detail": "Invalid credentials"}, None)
    # only real accounts are tracked, so random names cannot fill/evict the maps
    assert not login_lockout._global.get("ghost")
    assert all(not k.startswith("ghost|") for k in list(login_lockout._fails) + list(login_lockout._locked))


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


def test_flooding_pairs_never_evicts_an_active_lock(monkeypatch):
    import app.services.abuse as ab
    monkeypatch.setattr(ab, "MAX_TRACKED", 500)
    lo = ab.LoginLockout()
    for _ in range(10):
        lo.record_fail("admin", "9.9.9.9", 10, 900, now=100.0)
    assert lo.is_locked("admin", "9.9.9.9", now=101.0)
    for i in range(5000):
        lo.record_fail(f"u{i}", f"10.{i % 250}.{i // 250}.1", 10, 900, now=102.0)
    assert lo.is_locked("admin", "9.9.9.9", now=103.0)
    assert len(lo._fails) <= 500


async def _throttle_admin(client, session):
    for i in range(31):
        await client.post("/api/auth/login", headers={"X-Forwarded-For": f"203.0.113.{i + 1}"},
                          json={"username": "boss", "password": "nope"})
    # attacker keeps the shared 10 s slot busy
    await client.post("/api/auth/login", headers={"X-Forwarded-For": "198.51.100.1"},
                      json={"username": "boss", "password": "nope"})


async def test_device_cookie_bypasses_throttle_and_lock(client, session):
    await _make_user(session, "boss")
    good = {"username": "boss", "password": "correct horse battery staple"}
    r = await client.post("/api/auth/login", headers={"X-Forwarded-For": "1.1.1.1"}, json=good)
    assert r.status_code == 200
    sc = [c for c in r.headers.get_list("set-cookie") if c.startswith("styx_device=")]
    assert sc and "HttpOnly" in sc[0] and "Path=/api/auth" in sc[0] and "SameSite=strict" in sc[0]
    device = client.cookies.get("styx_device")
    client.cookies.clear()
    await _throttle_admin(client, session)
    h = {"X-Forwarded-For": "198.51.100.9"}
    # without the cookie: throttled
    assert (await client.post("/api/auth/login", headers=h, json=good)).status_code == 401
    # with it: signs in at once, even from a locked (user, ip)
    client.cookies.set("styx_device", device, path="/api/auth")
    assert (await client.post("/api/auth/login", headers=h, json=good)).status_code == 200


async def test_device_cookie_for_another_user_or_old_version_is_ignored(client, session):
    from sqlmodel import select
    from app.models import User
    await _make_user(session, "boss")
    await _make_user(session, "other")
    good = {"username": "boss", "password": "correct horse battery staple"}
    await client.post("/api/auth/login", json={"username": "other",
                      "password": "correct horse battery staple"})
    other_dev = client.cookies.get("styx_device")
    client.cookies.clear()
    await client.post("/api/auth/login", json=good)
    boss_dev = client.cookies.get("styx_device")
    client.cookies.clear()
    await _throttle_admin(client, session)
    h = {"X-Forwarded-For": "198.51.100.9"}
    client.cookies.set("styx_device", other_dev, path="/api/auth")
    assert (await client.post("/api/auth/login", headers=h, json=good)).status_code == 401
    u = (await session.exec(select(User).where(User.username == "boss"))).first()
    u.token_version += 1
    session.add(u)
    await session.commit()
    client.cookies.clear()
    client.cookies.set("styx_device", boss_dev, path="/api/auth")
    assert (await client.post("/api/auth/login", headers=h, json=good)).status_code == 401


def test_device_cookie_is_stripped_before_upstream():
    from app.security.cookies import strip_styx_cookies
    assert strip_styx_cookies("a=1; styx_device=zzz") == "a=1"


async def test_device_cookie_has_its_own_failure_budget(client, session):
    await _make_user(session, "boss")
    good = {"username": "boss", "password": "correct horse battery staple"}
    await client.post("/api/auth/login", headers={"X-Forwarded-For": "1.1.1.1"}, json=good)
    device = client.cookies.get("styx_device")
    client.cookies.clear()
    await _throttle_admin(client, session)
    client.cookies.set("styx_device", device, path="/api/auth")
    # a script holding the cookie guesses: bypass works for the first LOCKOUT_THRESHOLD misses
    for i in range(10):
        r = await client.post("/api/auth/login",
                              headers={"X-Forwarded-For": f"192.0.2.{i + 1}"},
                              json={"username": "boss", "password": "nope"})
        assert r.status_code == 401
    # budget spent: the cookie no longer bypasses, so the throttle applies like any client
    r = await client.post("/api/auth/login", headers={"X-Forwarded-For": "192.0.2.99"}, json=good)
    assert r.status_code == 401


async def test_successful_login_rotates_the_device_token(client, session):
    await _make_user(session, "boss")
    good = {"username": "boss", "password": "correct horse battery staple"}
    await client.post("/api/auth/login", json=good)
    first = client.cookies.get("styx_device")
    await client.post("/api/auth/login", json=good)
    assert client.cookies.get("styx_device") != first


def test_device_budget_is_bounded_and_blocks_survive(monkeypatch):
    import app.services.abuse as ab
    monkeypatch.setattr(ab, "MAX_TRACKED", 100)
    lo = ab.LoginLockout()
    for _ in range(10):
        lo.device_fail("victim-rnd", 10, 900, now=1.0)
    assert lo.device_blocked("victim-rnd", now=2.0)
    for i in range(1000):
        lo.device_fail(f"r{i}", 10, 900, now=3.0)
    assert lo.device_blocked("victim-rnd", now=4.0)
    assert len(lo._device_fails) <= 100
    assert not lo.device_blocked("victim-rnd", now=1000.0)
