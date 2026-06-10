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


def _groups(claims: dict, role_map: dict | None) -> list[str]:
    claim = (role_map or {}).get("claim") or "groups"
    present = claims.get(claim) or []
    if isinstance(present, str):
        present = [present]
    return list(present)


def _elevate(role: str, claims: dict, role_map: dict | None) -> str:
    """Already-authorized users (existing/invite): admin-group membership bumps to admin."""
    admin_group = (role_map or {}).get("admin_group")
    if admin_group and admin_group in _groups(claims, role_map):
        return "admin"
    return role


def _signup_role(claims: dict, role_map: dict | None) -> str | None:
    """Role for invite-less self-service signup, or None if not permitted.

    admin group → admin; if a user group is configured it is required for 'user';
    if no user group is configured, signup is open and grants 'user'.
    """
    rm = role_map or {}
    groups = _groups(claims, rm)
    if rm.get("admin_group") and rm["admin_group"] in groups:
        return "admin"
    user_group = rm.get("user_group")
    if user_group:
        return "user" if user_group in groups else None
    return "user"


async def _provision(session: AsyncSession, provider_name: str,
                     identity: OAuthIdentity, role: str) -> User:
    username = identity.email.split("@")[0]
    if (await session.exec(select(User).where(User.username == username))).first():
        username = f"{username}-{identity.sub[:6]}"
    user = User(username=username, email=identity.email,
                password_hash="!sso-no-password", role=role)
    session.add(user)
    await session.flush()
    session.add(FederatedIdentity(user_id=user.id, provider=provider_name,
                                  subject=identity.sub, email=identity.email))
    await session.commit()
    return user


async def resolve_identity(session: AsyncSession, provider_name: str,
                           identity: OAuthIdentity, role_map: dict | None = None,
                           trust_email: bool = False, allow_signup: bool = False) -> User:
    if not identity.email:
        raise EmailUnverified("IdP did not provide an email")
    if not identity.email_verified and not trust_email:
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
        role = _elevate(invite.role, identity.claims, role_map)
        invite.used_at = _now()
        session.add(invite)
        return await _provision(session, provider_name, identity, role)

    # 4. provider allows self-service signup → provision if the group gate permits
    if allow_signup:
        role = _signup_role(identity.claims, role_map)
        if role is not None:
            return await _provision(session, provider_name, identity, role)

    # 5. not pre-authorized
    raise NotAuthorized("email is not authorized to sign in")


async def link_identity(session: AsyncSession, user: User, provider_name: str,
                        identity: OAuthIdentity) -> None:
    # Linking is account-takeover surface (COAT): always require a verified
    # email regardless of the provider's trust_email login setting.
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
