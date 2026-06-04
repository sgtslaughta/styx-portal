from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import OAuthProvider, User
from app.schemas import ProviderCreate, ProviderUpdate, ProviderOut
from app.security.crypto import encrypt_secret
from app.security.deps import require_admin

router = APIRouter()


def _out(p: OAuthProvider) -> ProviderOut:
    return ProviderOut(id=p.id, name=p.name, display_label=p.display_label, kind=p.kind,
                       issuer_url=p.issuer_url, client_id=p.client_id, scopes=p.scopes,
                       role_map=p.role_map, enabled=p.enabled,
                       has_secret=bool(p.client_secret_enc),
                       icon_url=p.icon_url, trust_email=p.trust_email)


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


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    p = await session.get(OAuthProvider, provider_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(p)
    await session.commit()
