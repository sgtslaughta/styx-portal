"""Matrix card: enrollment (generate, activate, remove) and the login second step."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.middleware.rate_limit import client_ip_resolved
from app.routers.auth import _issue_session
from app.security import tokens
from app.security.cookies import DEVICE_COOKIE, MFA_COOKIE, clear_mfa_cookie, set_device_cookie
from app.security.deps import get_current_user
from app.security.passwords import verify_password
from app.services import login_flow, matrix_card
from app.services.audit import audit_request

router = APIRouter()


class PasswordBody(BaseModel):
    password: str


class ActivateBody(BaseModel):
    answer: str


class MatrixLoginBody(BaseModel):
    answers: list[str]


def clear_matrix(user: User) -> None:
    user.matrix_card = None
    user.matrix_pending = None
    user.matrix_challenge = None
    user.matrix_serial += 1


def _check_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Password is incorrect")


@router.get("/matrix")
async def matrix_status(user: User = Depends(get_current_user)):
    return {"enabled": bool(user.matrix_card)}


@router.post("/matrix/generate")
async def matrix_generate(body: PasswordBody, request: Request,
                          user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    _check_password(user, body.password)
    cells = matrix_card.generate_card()
    confirm = matrix_card.pick_challenge(1)[0]
    user.matrix_pending = matrix_card.seal({"cells": cells, "confirm": confirm})
    session.add(user)
    await audit_request(session, request, "matrix.generated", user_id=user.id)
    await session.commit()
    return {"cells": cells, "confirm_cell": confirm}


@router.post("/matrix/activate")
async def matrix_activate(body: ActivateBody, request: Request,
                          user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    if not user.matrix_pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No card pending")
    pending = matrix_card.unseal(user.matrix_pending)
    if not matrix_card.verify(pending["cells"], [pending["confirm"]], [body.answer]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wrong answer")
    user.matrix_card = matrix_card.seal(pending["cells"])
    user.matrix_pending = None
    user.matrix_challenge = None
    user.matrix_serial += 1
    session.add(user)
    await audit_request(session, request, "matrix.activated", user_id=user.id)
    await session.commit()
    return {"enabled": True}


@router.delete("/matrix")
async def matrix_remove(body: PasswordBody, request: Request,
                        user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    _check_password(user, body.password)
    clear_matrix(user)
    session.add(user)
    await audit_request(session, request, "matrix.removed", user_id=user.id)
    await session.commit()
    return {"enabled": False}


async def _pending_user(request: Request, session: AsyncSession) -> User:
    """The user whose password step this styx_mfa cookie proves, still awaiting the card."""
    expired = HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign-in expired")
    try:
        claims = tokens.decode_token(request.cookies.get(MFA_COOKIE) or "")
    except tokens.TokenError:
        raise expired
    user = await session.get(User, claims.get("sub")) if claims.get("type") == "mfa" else None
    if (not user or not user.is_active or not user.matrix_card or not user.matrix_challenge
            or claims.get("tv") != user.token_version
            or claims.get("serial") != user.matrix_serial):
        raise expired
    return user


@router.post("/login/matrix")
async def login_matrix(body: MatrixLoginBody, request: Request, response: Response,
                       session: AsyncSession = Depends(get_session)):
    user = await _pending_user(request, session)
    ip, resolved = client_ip_resolved(request)
    rnd = tokens.device_rnd(request.cookies.get(DEVICE_COOKIE), user)
    if login_flow.blocked(user.username, ip, rnd):
        await audit_request(session, request, "auth.login_locked", user_id=user.id)
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
    challenge = json.loads(user.matrix_challenge)
    if not matrix_card.verify(matrix_card.unseal(user.matrix_card), challenge, body.answers):
        await login_flow.record_failure(
            session, request, username=user.username, ip=ip, resolved=resolved, rnd=rnd,
            track_user=True, action="auth.matrix_failed", user_id=user.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid code")
    user.matrix_challenge = None
    login_flow.clear_lockout(session, user, ip, rnd)
    await _issue_session(response, session, user, request, session_only=True)
    set_device_cookie(response, tokens.create_device_token(user.id, user.token_version))
    clear_mfa_cookie(response)
    await audit_request(session, request, "auth.login", user_id=user.id,
                        detail={"method": "matrix"})
    await session.commit()
    return {"id": user.id, "username": user.username, "role": user.role,
            "must_change_pw": user.must_change_pw}
