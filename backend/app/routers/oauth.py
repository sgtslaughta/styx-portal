import logging

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import OAuthProvider
from app.schemas import PublicProvider
from app.security import oauth
from app.routers.auth import _issue_session
from app.services import federation

router = APIRouter()
logger = logging.getLogger("styx-portal")
_settings = Settings()


async def _get_enabled(session: AsyncSession, name: str) -> OAuthProvider | None:
    return (await session.exec(select(OAuthProvider).where(
        OAuthProvider.name == name, OAuthProvider.enabled == True))).first()  # noqa: E712


def _set_tx_cookie(resp: Response, tx: str) -> None:
    resp.set_cookie(oauth.TX_COOKIE, tx, max_age=oauth.TX_TTL, httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")


def _err_redirect(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?error={code}", status_code=status.HTTP_302_FOUND)


@router.get("/providers", response_model=list[PublicProvider])
async def list_public_providers(session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(OAuthProvider).where(
        OAuthProvider.enabled == True))).all()  # noqa: E712
    return [PublicProvider(name=p.name, display_label=p.display_label,
                           icon_url=p.icon_url) for p in rows]


@router.get("/{name}/start")
async def start(name: str, session: AsyncSession = Depends(get_session)):
    provider = await _get_enabled(session, name)
    if not provider:
        return _err_redirect("unknown_provider")
    url, state, verifier = await oauth.build_authorize(provider, mode="login")
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    _set_tx_cookie(resp, oauth.pack_tx(name, state, verifier, "login", None))
    return resp


@router.get("/{name}/callback")
async def callback(name: str, request: Request, session: AsyncSession = Depends(get_session)):
    tx_raw = request.cookies.get(oauth.TX_COOKIE)
    if not tx_raw:
        return _err_redirect("missing_state")
    try:
        tx = oauth.unpack_tx(tx_raw)
    except Exception:
        return _err_redirect("bad_state")
    if tx["provider"] != name or tx["mode"] != "login":
        return _err_redirect("bad_state")
    if request.query_params.get("state") != tx["state"]:
        return _err_redirect("state_mismatch")
    provider = await _get_enabled(session, name)
    if not provider:
        return _err_redirect("unknown_provider")
    try:
        identity = await oauth.fetch_identity(
            provider, "login", str(request.url), tx["verifier"])
        user = await federation.resolve_identity(
            session, name, identity, provider.role_map, provider.trust_email,
            provider.allow_signup)
    except federation.EmailUnverified:
        return _err_redirect("email_unverified")
    except federation.Disabled:
        return _err_redirect("account_disabled")
    except federation.NotAuthorized:
        return _err_redirect("not_authorized")
    except Exception:
        logger.exception("oauth callback failed")
        return _err_redirect("oauth_failed")
    resp = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie(oauth.TX_COOKIE)
    await _issue_session(resp, session, user, request)
    return resp
