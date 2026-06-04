import pytest

from app.models import User, Invite, FederatedIdentity
from app.schemas import OAuthIdentity
from app.security.passwords import hash_password
from app.services import federation


def _ident(sub="s1", email="a@b.c", verified=True, claims=None):
    return OAuthIdentity(sub=sub, email=email, email_verified=verified, claims=claims or {})


@pytest.mark.asyncio
async def test_reject_unverified_email(session):
    with pytest.raises(federation.EmailUnverified):
        await federation.resolve_identity(session, "google", _ident(verified=False))


@pytest.mark.asyncio
async def test_existing_identity_logs_in(session):
    u = User(username="bob", password_hash=hash_password("x"))
    session.add(u)
    await session.flush()
    session.add(FederatedIdentity(user_id=u.id, provider="google", subject="s1", email="a@b.c"))
    await session.commit()
    out = await federation.resolve_identity(session, "google", _ident())
    assert out.id == u.id


@pytest.mark.asyncio
async def test_links_existing_user_by_verified_email(session):
    u = User(username="bob", email="a@b.c", password_hash=hash_password("x"))
    session.add(u)
    await session.commit()
    out = await federation.resolve_identity(session, "google", _ident())
    assert out.id == u.id
    from sqlmodel import select
    rows = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.provider == "google"))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_provisions_via_open_invite(session):
    session.add(Invite(token_hash="h", email="a@b.c", role="user", created_by="admin"))
    await session.commit()
    out = await federation.resolve_identity(session, "google", _ident())
    assert out.email == "a@b.c"
    assert out.role == "user"


@pytest.mark.asyncio
async def test_rejects_when_not_preauthorized(session):
    with pytest.raises(federation.NotAuthorized):
        await federation.resolve_identity(session, "google", _ident(email="stranger@x.com"))


@pytest.mark.asyncio
async def test_role_map_promotes_admin(session):
    session.add(Invite(token_hash="h", email="a@b.c", role="user", created_by="admin"))
    await session.commit()
    role_map = {"claim": "groups", "admin_group": "selkies-admins"}
    out = await federation.resolve_identity(
        session, "google", _ident(claims={"groups": ["selkies-admins"]}), role_map=role_map)
    assert out.role == "admin"


@pytest.mark.asyncio
async def test_rejects_disabled_user(session):
    u = User(username="bob", email="a@b.c", password_hash=hash_password("x"), is_active=False)
    session.add(u)
    await session.commit()
    with pytest.raises(federation.Disabled):
        await federation.resolve_identity(session, "google", _ident())


@pytest.mark.asyncio
async def test_trust_email_allows_unverified(session):
    session.add(Invite(token_hash="h", email="a@b.c", role="user", created_by="admin"))
    await session.commit()
    out = await federation.resolve_identity(
        session, "authentik", _ident(verified=False), trust_email=True)
    assert out.email == "a@b.c"


@pytest.mark.asyncio
async def test_no_email_always_rejected_even_with_trust(session):
    with pytest.raises(federation.EmailUnverified):
        await federation.resolve_identity(
            session, "authentik", _ident(verified=False, email=None), trust_email=True)


def _claims(groups=None):
    return {"groups": groups or []}


@pytest.mark.asyncio
async def test_no_signup_without_allow_signup(session):
    # default: invite-less, allow_signup off -> NotAuthorized
    with pytest.raises(federation.NotAuthorized):
        await federation.resolve_identity(session, "authentik", _ident())


@pytest.mark.asyncio
async def test_allow_signup_open_provisions_user(session):
    out = await federation.resolve_identity(
        session, "authentik", _ident(), role_map={}, allow_signup=True)
    assert out.email == "a@b.c"
    assert out.role == "user"


@pytest.mark.asyncio
async def test_signup_requires_user_group_when_set(session):
    rm = {"claim": "groups", "user_group": "styx-users", "admin_group": "styx-admins"}
    # not in user group -> denied even with allow_signup
    with pytest.raises(federation.NotAuthorized):
        await federation.resolve_identity(
            session, "authentik",
            _ident(claims=_claims(["other"])), role_map=rm, allow_signup=True)


@pytest.mark.asyncio
async def test_signup_user_group_grants_user(session):
    rm = {"claim": "groups", "user_group": "styx-users", "admin_group": "styx-admins"}
    out = await federation.resolve_identity(
        session, "authentik",
        _ident(claims=_claims(["styx-users"])), role_map=rm, allow_signup=True)
    assert out.role == "user"


@pytest.mark.asyncio
async def test_signup_admin_group_grants_admin(session):
    rm = {"claim": "groups", "user_group": "styx-users", "admin_group": "styx-admins"}
    out = await federation.resolve_identity(
        session, "authentik",
        _ident(claims=_claims(["styx-admins"])), role_map=rm, allow_signup=True)
    assert out.role == "admin"
