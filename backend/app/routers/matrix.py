"""Matrix card enrollment: generate, activate, remove."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.security.deps import get_current_user
from app.security.passwords import verify_password
from app.services import matrix_card
from app.services.audit import audit_request

router = APIRouter()


class PasswordBody(BaseModel):
    password: str


class ActivateBody(BaseModel):
    answer: str


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
