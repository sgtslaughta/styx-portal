from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import User, Invite, FederatedIdentity
from app.schemas import OAuthIdentity


class FederationError(Exception):
    pass


class EmailUnverified(FederationError):
    pass


class NotAuthorized(FederationError):
    pass


class Disabled(FederationError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _apply_role_map(default_role: str, claims: dict, role_map: dict | None) -> str:
    if not role_map:
        return default_role
    claim = role_map.get("claim")
    values = role_map.get("values", {})
    present = claims.get(claim) or []
    if isinstance(present, str):
        present = [present]
    for group in present:
        if group in values:
            return values[group]
    return default_role


async def resolve_identity(session: AsyncSession, provider_name: str,
                           identity: OAuthIdentity, role_map: dict | None = None) -> User:
    if not identity.email_verified or not identity.email:
        raise EmailUnverified("IdP did not provide a verified email")

    # 1. existing federated identity → login
    fi = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.provider == provider_name,
        FederatedIdentity.subject == identity.sub))).first()
    if fi:
        user = await session.get(User, fi.user_id)
        if not user or not user.is_active:
            raise Disabled("account disabled")
        return user

    # 2. verified email matches an existing user → link
    existing = (await session.exec(select(User).where(User.email == identity.email))).first()
    if existing:
        if not existing.is_active:
            raise Disabled("account disabled")
        session.add(FederatedIdentity(user_id=existing.id, provider=provider_name,
                                      subject=identity.sub, email=identity.email))
        await session.commit()
        return existing

    # 3. verified email matches an open invite → provision
    invite = (await session.exec(select(Invite).where(
        Invite.email == identity.email, Invite.used_at == None))).first()  # noqa: E711
    if invite and not (invite.expires_at and invite.expires_at < _now()):
        role = _apply_role_map(invite.role, identity.claims, role_map)
        username = identity.email.split("@")[0]
        if (await session.exec(select(User).where(User.username == username))).first():
            username = f"{username}-{identity.sub[:6]}"
        user = User(username=username, email=identity.email, password_hash="!sso-no-password",
                    role=role)
        invite.used_at = _now()
        session.add_all([user, invite])
        await session.flush()
        session.add(FederatedIdentity(user_id=user.id, provider=provider_name,
                                      subject=identity.sub, email=identity.email))
        await session.commit()
        return user

    # 4. not pre-authorized
    raise NotAuthorized("email is not authorized to sign in")


async def link_identity(session: AsyncSession, user: User, provider_name: str,
                        identity: OAuthIdentity) -> None:
    if not identity.email_verified:
        raise EmailUnverified("IdP did not provide a verified email")
    taken = (await session.exec(select(FederatedIdentity).where(
        FederatedIdentity.provider == provider_name,
        FederatedIdentity.subject == identity.sub))).first()
    if taken and taken.user_id != user.id:
        raise NotAuthorized("identity already linked to another account")
    if not taken:
        session.add(FederatedIdentity(user_id=user.id, provider=provider_name,
                                      subject=identity.sub, email=identity.email))
        await session.commit()
