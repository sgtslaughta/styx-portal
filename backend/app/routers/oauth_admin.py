from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import OAuthProvider, User
from app.schemas import ProviderCreate, ProviderUpdate, ProviderOut, ProviderTestResult
from app.security import oauth
from app.security.crypto import encrypt_secret
from app.security.deps import require_admin
import json as _json

_settings = Settings()

router = APIRouter()


def _login_redirect_uri(name: str) -> str:
    # canonical login-flow callback — exactly what build_authorize sends to the IdP
    return oauth._redirect_uri(name, "login")


def _test_redirect_uri(provider_id: str) -> str:
    return f"{_settings.oauth_redirect_base()}/api/oauth-providers/{provider_id}/test/callback"


def _out(p: OAuthProvider) -> ProviderOut:
    return ProviderOut(id=p.id, name=p.name, display_label=p.display_label, kind=p.kind,
                       issuer_url=p.issuer_url, client_id=p.client_id, scopes=p.scopes,
                       role_map=p.role_map, enabled=p.enabled,
                       has_secret=bool(p.client_secret_enc),
                       icon_url=p.icon_url, trust_email=bool(p.trust_email),
                       redirect_uri=_login_redirect_uri(p.name),
                       test_redirect_uri=_test_redirect_uri(p.id))


MAX_ICON_BYTES = 256 * 1024


def _validate_icon(icon_url: str | None) -> None:
    if icon_url and icon_url.startswith("data:"):
        if not icon_url.startswith("data:image/"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "icon must be an image data URI")
        if len(icon_url) > MAX_ICON_BYTES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "icon data URI too large (max 256KB)")


@router.get("", response_model=list[ProviderOut])
async def list_providers(admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(OAuthProvider))).all()
    return [_out(p) for p in rows]


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(body: ProviderCreate, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    if body.kind not in ("oidc", "oauth2"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind must be oidc|oauth2")
    _validate_icon(body.icon_url)
    if (await session.exec(select(OAuthProvider).where(OAuthProvider.name == body.name))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "provider name taken")
    p = OAuthProvider(
        name=body.name, display_label=body.display_label, kind=body.kind,
        issuer_url=body.issuer_url, authorize_url=body.authorize_url,
        token_url=body.token_url, userinfo_url=body.userinfo_url,
        client_id=body.client_id, client_secret_enc=encrypt_secret(body.client_secret),
        scopes=body.scopes, role_map=body.role_map, enabled=body.enabled,
        icon_url=body.icon_url, trust_email=body.trust_email)
    session.add(p)
    await session.commit()
    return _out(p)


@router.patch("/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, body: ProviderUpdate,
                          admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    data = body.model_dump(exclude_unset=True)
    if "icon_url" in data:
        _validate_icon(data["icon_url"])
    if "client_secret" in data and data["client_secret"]:
        p.client_secret_enc = encrypt_secret(data.pop("client_secret"))
    else:
        data.pop("client_secret", None)
    for k, v in data.items():
        setattr(p, k, v)
    p.updated_at = datetime.now(timezone.utc)
    session.add(p)
    await session.commit()
    return _out(p)


@router.post("/{provider_id}/test/config", response_model=ProviderTestResult)
async def test_config(provider_id: str, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    ok, checks = await oauth.discovery_checks(p)
    return ProviderTestResult(ok=ok, checks=checks)


@router.get("/{provider_id}/test/start")
async def test_start(provider_id: str, admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    redirect = _test_redirect_uri(provider_id)
    url, state, verifier = await oauth.build_authorize(p, mode="test", redirect_uri=redirect)
    resp = RedirectResponse(url, status_code=status.HTTP_302_FOUND)
    resp.set_cookie(oauth.TX_COOKIE,
                    oauth.pack_tx(p.name, state, verifier, "test", provider_id),
                    max_age=oauth.TX_TTL, httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")
    return resp


# Scoped CSP for the probe page only: it serves a single inline <script> that
# postMessages the result to its opener. The global script-src 'self' policy would
# block that inline script, so this response carries its own minimal policy.
_PROBE_CSP = "default-src 'none'; script-src 'unsafe-inline'"


def _probe_page(probe: dict) -> HTMLResponse:
    payload = _json.dumps(probe).replace("<", "\\u003c")
    html = (
        "<!doctype html><html><body><script>"
        f"const r={payload};"
        "if(window.opener){window.opener.postMessage({type:'sso-test',result:r},window.location.origin);}"
        "document.body.innerText=JSON.stringify(r,null,2);"
        "setTimeout(()=>window.close(),500);"
        "</script></body></html>"
    )
    return HTMLResponse(html, headers={"Content-Security-Policy": _PROBE_CSP})


@router.get("/{provider_id}/test/callback")
async def test_callback(provider_id: str, request: Request,
                        admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    tx_raw = request.cookies.get(oauth.TX_COOKIE)
    try:
        tx = oauth.unpack_tx(tx_raw or "")
    except Exception:
        return _probe_page({"ok": False, "error": "bad_state"})
    if tx["mode"] != "test" or tx["uid"] != provider_id or \
            request.query_params.get("state") != tx["state"]:
        return _probe_page({"ok": False, "error": "state_mismatch"})
    redirect = _test_redirect_uri(provider_id)
    try:
        identity = await oauth.fetch_identity(p, "test", str(request.url),
                                              tx["verifier"], redirect_uri=redirect)
    except Exception as e:  # noqa: BLE001
        return _probe_page({"ok": False, "error": str(e)})
    would_pass = bool(identity.email) and (identity.email_verified or p.trust_email)
    probe = {"ok": True, "sub": identity.sub, "email": identity.email,
             "email_verified": identity.email_verified, "trust_email": p.trust_email,
             "would_pass": would_pass, "claims": identity.claims}
    resp = _probe_page(probe)
    resp.delete_cookie(oauth.TX_COOKIE)
    return resp


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(p)
    await session.commit()
