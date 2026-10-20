"""Matrix card as the second step of password login."""
import json
from unittest.mock import AsyncMock, patch

from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models import Invite, OAuthProvider, RefreshToken, User
from app.schemas import OAuthIdentity
from app.security.crypto import encrypt_secret
from app.security.passwords import hash_password
from app.services import matrix_card

PW = "correct horse battery staple"


async def _card_user(session, name="carol"):
    card = matrix_card.generate_card()
    session.add(User(username=name, password_hash=hash_password(PW), role="member",
                     is_active=True, matrix_card=matrix_card.seal(card)))
    await session.commit()
    return card


async def _user(session, name="carol"):
    session.expire_all()
    return (await session.exec(select(User).where(User.username == name))).one()


async def _login(client, name="carol", pw=PW):
    return await client.post("/api/auth/login", json={"username": name, "password": pw})


def _set_cookie(r, name, deleted=False):
    """Set-Cookie headers for name; deletions (legacy Path=/ clears) only when asked."""
    return [h for h in r.headers.get_list("set-cookie")
            if h.startswith(f"{name}=") and h.startswith(f'{name}=""') == deleted]


async def test_password_login_without_card_unchanged(client, session):
    session.add(User(username="plain", password_hash=hash_password(PW), role="member",
                     is_active=True))
    await session.commit()
    r = await _login(client, "plain")
    assert r.status_code == 200
    assert "mfa_required" not in r.json() and r.json()["username"] == "plain"
    assert "Max-Age" in _set_cookie(r, "access_token")[0]
    assert not _set_cookie(r, "styx_mfa")


async def test_card_user_gets_challenge_no_session(client, session):
    await _card_user(session)
    r = await _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is True and len(set(body["challenge"])) == 3
    assert not _set_cookie(r, "access_token") and not _set_cookie(r, "styx_device")
    mfa = _set_cookie(r, "styx_mfa")[0]
    assert "HttpOnly" in mfa and "Path=/api/auth" in mfa and "Max-Age=300" in mfa
    assert "samesite=strict" in mfa.lower()
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_challenge_stable_across_logins(client, session):
    await _card_user(session)
    first = (await _login(client)).json()["challenge"]
    for _ in range(3):
        assert (await _login(client)).json()["challenge"] == first
    assert json.loads((await _user(session)).matrix_challenge) == first


async def test_matrix_success_issues_session_only_cookies(client, session):
    card = await _card_user(session)
    ch = (await _login(client)).json()["challenge"]
    r = await client.post("/api/auth/login/matrix",
                          json={"answers": [" " + card[c].lower() + " " for c in ch]})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "carol" and "must_change_pw" in r.json()
    for name in ("access_token", "refresh_token", "styx_proxy", "csrf_token"):
        hdr = _set_cookie(r, name)[0]
        assert "Max-Age" not in hdr and "expires" not in hdr.lower(), hdr
    assert not _set_cookie(r, "styx_device")  # public computer: no trusted-device cookie
    assert r.headers["cache-control"] == "no-store"
    assert "Path=/api/auth" in _set_cookie(r, "styx_mfa", deleted=True)[0]
    assert (await client.get("/api/auth/me")).status_code == 200
    assert (await _user(session)).matrix_challenge is None
    tok = (await session.exec(select(RefreshToken))).one()
    assert tok.session_only is True


async def test_matrix_wrong_counts_toward_lockout(client, session):
    card = await _card_user(session)
    ch = (await _login(client)).json()["challenge"]
    for _ in range(10):  # LOCKOUT_THRESHOLD default
        r = await client.post("/api/auth/login/matrix", json={"answers": ["XXX"] * 3})
        assert r.status_code == 401 and r.json()["detail"] == "Invalid code"
    assert json.loads((await _user(session)).matrix_challenge) == ch
    r = await client.post("/api/auth/login/matrix", json={"answers": [card[c] for c in ch]})
    assert r.status_code == 401
    assert (await _login(client)).status_code == 401


async def test_matrix_expired_token_401(client, session, monkeypatch):
    card = await _card_user(session)
    monkeypatch.setattr("app.security.tokens.MFA_TTL", -10)
    ch = (await _login(client)).json()["challenge"]
    r = await client.post("/api/auth/login/matrix", json={"answers": [card[c] for c in ch]})
    assert r.status_code == 401 and r.json()["detail"] == "Sign-in expired"
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_matrix_without_cookie_401(client, session):
    await _card_user(session)
    r = await client.post("/api/auth/login/matrix", json={"answers": ["A", "B", "C"]})
    assert r.status_code == 401 and r.json()["detail"] == "Sign-in expired"


async def test_matrix_after_regenerate_401(client, session):
    card = await _card_user(session)
    ch = (await _login(client)).json()["challenge"]
    u = await _user(session)
    u.matrix_serial += 1
    session.add(u)
    await session.commit()
    r = await client.post("/api/auth/login/matrix", json={"answers": [card[c] for c in ch]})
    assert r.status_code == 401 and r.json()["detail"] == "Sign-in expired"


async def test_locked_user_never_gets_challenge(client, session):
    await _card_user(session)
    for _ in range(10):
        await _login(client, pw="nope")
    r = await _login(client)
    assert r.status_code == 401 and "mfa_required" not in r.json()
    assert not _set_cookie(r, "styx_mfa")
    assert (await _user(session)).matrix_challenge is None


async def test_refresh_keeps_session_only(client, session):
    card = await _card_user(session)
    ch = (await _login(client)).json()["challenge"]
    await client.post("/api/auth/login/matrix", json={"answers": [card[c] for c in ch]})
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200, r.text
    assert "Max-Age" not in _set_cookie(r, "access_token")[0]
    assert "Max-Age" not in _set_cookie(r, "refresh_token")[0]
    toks = (await session.exec(select(RefreshToken))).all()
    assert len(toks) == 2 and all(t.session_only for t in toks)


async def test_oauth_login_ignores_card(client, session):
    session.add(OAuthProvider(name="google", display_label="Google", kind="oidc",
                              issuer_url="https://accounts.google.test",
                              client_id="cid", client_secret_enc=encrypt_secret("sec")))
    session.add(Invite(token_hash="h", email="new@x.com", role="user", created_by="a"))
    await session.commit()
    with patch("app.security.oauth.build_authorize",
               AsyncMock(return_value=("https://idp/auth", "STATE", "VERIFIER"))):
        await client.get("/api/auth/oauth/google/start", follow_redirects=False)
    ident = OAuthIdentity(sub="g-1", email="new@x.com", email_verified=True, claims={})
    real_resolve = __import__("app.services.federation", fromlist=["x"]).resolve_identity

    async def resolve_with_card(*a, **kw):
        user = await real_resolve(*a, **kw)
        user.matrix_card = matrix_card.seal(matrix_card.generate_card())
        return user

    with patch("app.security.oauth.fetch_identity", AsyncMock(return_value=ident)), \
            patch("app.services.federation.resolve_identity", resolve_with_card):
        r = await client.get("/api/auth/oauth/google/callback?state=STATE&code=abc",
                             follow_redirects=False)
    assert r.status_code == 302
    assert "Max-Age" in _set_cookie(r, "access_token")[0]
    assert not _set_cookie(r, "styx_mfa")
    assert (await session.exec(select(RefreshToken))).one().session_only is False


async def test_change_password_keeps_session_only(client, session):
    card = await _card_user(session)
    ch = (await _login(client)).json()["challenge"]
    await client.post("/api/auth/login/matrix", json={"answers": [card[c] for c in ch]})
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    r = await client.post("/api/auth/change-password",
                          json={"old_password": PW, "new_password": PW + " v2 rotated!"})
    assert r.status_code == 200, r.text
    assert "Max-Age" not in _set_cookie(r, "access_token")[0]
    live = (await session.exec(select(RefreshToken).where(
        RefreshToken.revoked == False))).all()  # noqa: E712
    assert len(live) == 1 and live[0].session_only is True


async def test_matrix_step_not_throttled_after_password(client, session):
    card = await _card_user(session)
    for i in range(30):  # LOGIN_GLOBAL_THRESHOLD: distributed guessing engages the brake
        await client.post("/api/auth/login", headers={"X-Forwarded-For": f"203.0.113.{i + 1}"},
                          json={"username": "carol", "password": "nope"})
    h = {"X-Forwarded-For": "198.51.100.7"}
    r = await client.post("/api/auth/login", headers=h, json={"username": "carol", "password": PW})
    assert r.status_code == 200 and r.json()["mfa_required"] is True
    ch = r.json()["challenge"]
    r = await client.post("/api/auth/login/matrix", headers=h,
                          json={"answers": [card[c] for c in ch]})
    assert r.status_code == 200, r.text


async def _age_family(session, hours):
    for t in (await session.exec(select(RefreshToken))).all():
        t.created_at = datetime.now(timezone.utc) - timedelta(hours=hours)
        session.add(t)
    await session.commit()


async def test_session_only_family_capped(client, session):
    card = await _card_user(session)
    ch = (await _login(client)).json()["challenge"]
    await client.post("/api/auth/login/matrix", json={"answers": [card[c] for c in ch]})
    await _age_family(session, 13)  # MATRIX_SESSION_MAX_HOURS default 12
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 401 and r.json()["detail"] == "Session expired"


async def test_persistent_family_not_capped(client, session):
    session.add(User(username="plain", password_hash=hash_password(PW), role="member",
                     is_active=True))
    await session.commit()
    assert (await _login(client, "plain")).status_code == 200
    await _age_family(session, 13)
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    assert (await client.post("/api/auth/refresh")).status_code == 200
