from datetime import datetime, timedelta, timezone

import httpx
import jwt
from authlib.common.security import generate_token
from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.config import Settings
from app.models import OAuthProvider
from app.schemas import OAuthIdentity
from app.security.crypto import decrypt_secret

_settings = Settings()
_ALGO = "HS256"
TX_COOKIE = "oauth_tx"
TX_TTL = 600  # 10 minutes

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_USER = "https://api.github.com/user"
GITHUB_EMAILS = "https://api.github.com/user/emails"


# ---- pure helpers ----
def normalize_oidc(userinfo: dict) -> OAuthIdentity:
    return OAuthIdentity(
        sub=str(userinfo.get("sub")),
        email=userinfo.get("email"),
        email_verified=bool(userinfo.get("email_verified", False)),
        claims=userinfo,
    )


def select_github_email(emails: list[dict]) -> str | None:
    for e in emails:
        if e.get("primary") and e.get("verified"):
            return e["email"]
    for e in emails:
        if e.get("verified"):
            return e["email"]
    return None


def pack_tx(provider: str, state: str, verifier: str, mode: str, uid: str | None) -> str:
    now = datetime.now(timezone.utc)
    payload = {"provider": provider, "state": state, "verifier": verifier,
               "mode": mode, "uid": uid, "type": "oauth_tx",
               "iat": now, "exp": now + timedelta(seconds=TX_TTL)}
    return jwt.encode(payload, _settings.jwt_secret_or_raise(), algorithm=_ALGO)


def unpack_tx(token: str) -> dict:
    return jwt.decode(token, _settings.jwt_secret_or_raise(), algorithms=[_ALGO])


# ---- network orchestration (mocked in router tests) ----
async def _discover(issuer: str) -> dict:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.json()


async def _endpoints(provider: OAuthProvider) -> dict:
    if provider.kind == "oidc":
        d = await _discover(provider.issuer_url)
        return {"authorize": d["authorization_endpoint"], "token": d["token_endpoint"],
                "userinfo": d["userinfo_endpoint"]}
    if provider.name == "github":
        return {"authorize": GITHUB_AUTHORIZE, "token": GITHUB_TOKEN, "userinfo": GITHUB_USER}
    return {"authorize": provider.authorize_url, "token": provider.token_url,
            "userinfo": provider.userinfo_url}


async def discovery_checks(provider: OAuthProvider) -> tuple[bool, list[dict]]:
    """Server-side reachability/validity checks. Never raises."""
    checks: list[dict] = []
    checks.append({"label": "client_id set", "ok": bool(provider.client_id),
                   "detail": "" if provider.client_id else "missing"})
    try:
        eps = await _endpoints(provider)
        src = "discovery" if provider.kind == "oidc" else "config"
        for key in ("authorize", "token", "userinfo"):
            val = eps.get(key)
            checks.append({"label": f"{key} endpoint", "ok": bool(val),
                           "detail": val or f"missing in {src}"})
    except Exception as e:  # noqa: BLE001 — surface, never 500
        checks.append({"label": "endpoint discovery", "ok": False, "detail": str(e)})
    ok = all(c["ok"] for c in checks)
    return ok, checks


def _redirect_uri(provider_name: str, mode: str) -> str:
    leg = "link" if mode == "link" else "oauth"
    return f"{_settings.oauth_redirect_base()}/api/auth/{leg}/{provider_name}/callback"


async def build_authorize(provider: OAuthProvider, mode: str,
                          redirect_uri: str | None = None) -> tuple[str, str, str]:
    """Returns (authorize_url, state, code_verifier)."""
    eps = await _endpoints(provider)
    client = AsyncOAuth2Client(
        provider.client_id, decrypt_secret(provider.client_secret_enc),
        scope=provider.scopes,
        redirect_uri=redirect_uri or _redirect_uri(provider.name, mode),
        code_challenge_method="S256",
    )
    verifier = generate_token(48)
    url, state = client.create_authorization_url(eps["authorize"], code_verifier=verifier)
    return url, state, verifier


async def fetch_identity(provider: OAuthProvider, mode: str,
                         authorization_response: str, verifier: str,
                         redirect_uri: str | None = None) -> OAuthIdentity:
    eps = await _endpoints(provider)
    client = AsyncOAuth2Client(
        provider.client_id, decrypt_secret(provider.client_secret_enc),
        scope=provider.scopes,
        redirect_uri=redirect_uri or _redirect_uri(provider.name, mode),
        code_challenge_method="S256",
    )
    headers = {"Accept": "application/json"} if provider.name == "github" else None
    await client.fetch_token(eps["token"], authorization_response=authorization_response,
                             code_verifier=verifier, headers=headers)
    if provider.name == "github":
        u = (await client.get(GITHUB_USER)).json()
        emails = (await client.get(GITHUB_EMAILS)).json()
        email = select_github_email(emails)
        return OAuthIdentity(sub=str(u["id"]), email=email,
                             email_verified=email is not None, claims=u)
    userinfo = (await client.get(eps["userinfo"])).json()
    return normalize_oidc(userinfo)
