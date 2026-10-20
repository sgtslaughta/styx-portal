"""Lockout gate, failure path and success clears shared by password and matrix login."""
import json

from fastapi import Request, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import User
from app.security import tokens
from app.security.cookies import set_mfa_cookie
from app.services import matrix_card
from app.services.abuse import ban_cache, ban_ip, fail_tracker, login_lockout
from app.services.audit import audit_request
from app.services.settings_store import settings as sys_settings

_settings = Settings()


def blocked(username: str, ip: str, rnd: str | None) -> bool:
    """Locked or throttled, unless a still-trusted device cookie for this account vouches."""
    if rnd is not None and not login_lockout.device_blocked(rnd):
        return False
    return (login_lockout.is_locked(username, ip)
            or login_lockout.throttled(username, _settings.LOGIN_GLOBAL_THRESHOLD,
                                       sys_settings.get("LOCKOUT_DURATION")))


async def record_failure(session: AsyncSession, request: Request, *, username: str, ip: str,
                         resolved: bool, rnd: str | None, track_user: bool,
                         action: str, **audit) -> None:
    if rnd:
        login_lockout.device_fail(rnd, sys_settings.get("LOCKOUT_THRESHOLD"),
                                  sys_settings.get("LOCKOUT_DURATION"))
    # Only real accounts are tracked (keeps the maps bounded by the user count).
    if track_user:
        login_lockout.record_fail(username, ip, sys_settings.get("LOCKOUT_THRESHOLD"),
                                  sys_settings.get("LOCKOUT_DURATION"))
    # Per-IP abuse detector -> proxy ban (L3). Thresholds are live-tunable.
    fail_tracker.threshold = sys_settings.get("BAN_FAIL_THRESHOLD")
    fail_tracker.window = sys_settings.get("BAN_FAIL_WINDOW")
    # Unresolved: still tracked under the peer address, but a misconfiguration must never
    # persist a ban on the proxy itself (it would lock out the whole portal).
    if fail_tracker.record(ip) and resolved:
        await ban_ip(session, ip, "brute-force: failed logins", sys_settings.get("BAN_DURATION"))
        ban_cache.invalidate()
    await audit_request(session, request, action, **audit)
    await session.commit()


def clear_lockout(session: AsyncSession, user: User, ip: str, rnd: str | None) -> None:
    user.failed_count = 0
    user.locked_until = None
    login_lockout.clear(user.username, ip)
    if rnd:
        login_lockout.device_clear(rnd)    # the fresh device cookie carries a new rnd
    session.add(user)


async def start_matrix(session: AsyncSession, request: Request, response: Response,
                       user: User) -> dict:
    """Password passed for a card user: pin a challenge (stable until answered) and hand
    out the short-lived styx_mfa cookie. No session and no lockout clears yet."""
    if not user.matrix_challenge:
        user.matrix_challenge = json.dumps(matrix_card.pick_challenge())
        session.add(user)
    set_mfa_cookie(response, tokens.create_mfa_token(user.id, user.token_version,
                                                     user.matrix_serial))
    await audit_request(session, request, "auth.matrix_challenge", user_id=user.id)
    await session.commit()
    return {"mfa_required": True, "challenge": json.loads(user.matrix_challenge)}
