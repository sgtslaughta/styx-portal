"""Admin "Check setup": verify TURN / Cloudflare settings actually work. Never returns secrets."""
import asyncio
from datetime import datetime, timezone

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Workstation
from app.services import cf_turn_usage
from app.services.settings_store import settings
from app.services.turn_usage import GB, month_bytes, turn_over_budget

CF_CRED_URL = "https://rtc.live.cloudflare.com/v1/turn/keys/{}/credentials/generate"
QUERY = """query($acct: String!, $from: Date!, $to: Date!) {
  viewer { accounts(filter: {accountTag: $acct}) {
    callsTurnUsageAdaptiveGroups(limit: 10000,
        filter: {date_geq: $from, date_leq: $to}) {
      dimensions { keyId } sum { egressBytes } } } } }"""


def _c(id_: str, label: str, status: str, detail: str) -> dict:
    return {"id": id_, "label": label, "status": status, "detail": detail}


def _fmt(b: int) -> str:
    return f"{b / GB:.1f} GB" if b >= GB else f"{b / 10 ** 6:.1f} MB"


def _tail(key: str) -> str:
    return f"…{key[-4:]}"


async def _credentials(c: httpx.AsyncClient) -> dict:
    label = "TURN credentials"
    tid, tok = settings.get("CLOUDFLARE_TURN_TOKEN_ID"), settings.get("CLOUDFLARE_TURN_API_TOKEN")
    if not (tid and tok):
        return _c("turn_credentials", label, "error", "TURN key ID and API token must both be set.")
    try:
        r = await c.post(CF_CRED_URL.format(tid), headers={"Authorization": f"Bearer {tok}"},
                         json={"ttl": 60}, timeout=10)
    except httpx.HTTPError as e:
        return _c("turn_credentials", label, "error", f"Network error: {str(e)[:150] or type(e).__name__}")
    if r.status_code in (401, 403):
        return _c("turn_credentials", label, "error", "API token rejected")
    if r.status_code == 404:
        return _c("turn_credentials", label, "error", "TURN key ID not found")
    if not 200 <= r.status_code < 300:
        return _c("turn_credentials", label, "error", f"Unexpected response: HTTP {r.status_code}")
    try:
        ice = r.json().get("iceServers") or []
        ice = [ice] if isinstance(ice, dict) else ice
        urls = [u for s in ice for u in ([s["urls"]] if isinstance(s.get("urls"), str)
                                          else s.get("urls") or [])]
    except (ValueError, AttributeError, TypeError):
        urls = []
    n = sum(1 for u in urls if str(u).startswith(("turn:", "turns:")))
    if not n:
        return _c("turn_credentials", label, "error", "Response contained no TURN URLs.")
    return _c("turn_credentials", label, "ok", f"Credentials issued with {n} TURN URL(s).")


async def _reachable() -> dict:
    label, host, port = "TURN server reachable", settings.get("TURN_HOST"), settings.get("TURN_PORT")
    note = " (UDP can't be verified from the server)"
    if not host:
        return _c("turn_reachable", label, "error", "TURN host is not set.")
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
        w.close()
    except (OSError, asyncio.TimeoutError) as e:
        return _c("turn_reachable", label, "error",
                  f"TCP connect to {host}:{port} failed: {str(e)[:100] or 'timeout'}{note}")
    return _c("turn_reachable", label, "ok", f"TCP connect to {host}:{port} succeeded{note}.")


async def _transport(session: AsyncSession, provider: str) -> dict:
    rows = (await session.exec(select(Workstation.stream_settings))).all()
    default = settings.get("WORKSTATION_TRANSPORT") or "websockets"
    n = 0
    for ss in rows:
        want = (ss or {}).get("transport")
        if (want if want in ("websockets", "webrtc") else default) == "webrtc":
            n += 1
    if provider != "none" and n == 0:
        return _c("transport", "WebRTC in use", "warn",
                  "TURN is configured but no workstation uses WebRTC. Set Default stream transport, "
                  "or a workstation's Stream settings → Transport, to WebRTC.")
    return _c("transport", "WebRTC in use", "ok", f"{n} workstation(s) use WebRTC")


async def _analytics(c: httpx.AsyncClient, now: datetime) -> tuple[list[dict], int | None]:
    label = "Cloudflare analytics"
    if not cf_turn_usage.configured():
        return [_c("analytics", label, "skip", "Set the account ID and analytics token to show "
                   "Cloudflare's actual usage on the cost card.")], None
    variables = {"acct": settings.get("CLOUDFLARE_ACCOUNT_ID"),
                 "from": now.strftime("%Y-%m-01"), "to": now.strftime("%Y-%m-%d")}
    headers = {"Authorization": f"Bearer {settings.get('CLOUDFLARE_ANALYTICS_TOKEN')}"}
    try:
        r = await c.post(cf_turn_usage.URL, json={"query": QUERY, "variables": variables},
                         headers=headers, timeout=10)
        body = r.json() if r.content else {}
    except (httpx.HTTPError, ValueError) as e:
        return [_c("analytics", label, "error", f"Request failed: {str(e)[:150]}")], None
    if r.status_code in (401, 403):
        return [_c("analytics", label, "error", "Analytics token rejected")], None
    errs = body.get("errors") if isinstance(body, dict) else None
    if r.status_code != 200 or errs:
        msg = str((errs or [{}])[0].get("message", f"HTTP {r.status_code}"))[:150]
        if "auth" in msg.lower() or "permission" in msg.lower():
            msg = "Analytics token rejected"
        return [_c("analytics", label, "error", msg)], None
    accts = (((body.get("data") or {}).get("viewer") or {}).get("accounts")) or []
    per: dict[str, int] = {}
    for a in accts:
        for g in a.get("callsTurnUsageAdaptiveGroups") or []:
            k = (g.get("dimensions") or {}).get("keyId") or ""
            per[k] = per.get(k, 0) + int((g.get("sum") or {}).get("egressBytes") or 0)
    ours = settings.get("CLOUDFLARE_TURN_TOKEN_ID")
    mine = per.get(ours, 0)
    out = [_c("analytics", label, "ok", f"{_fmt(mine)} relayed this month")]
    for k, b in per.items():
        if k != ours and b > 0:
            out.append(_c("other_keys", "Other TURN keys", "warn",
                          f"{_fmt(b)} relayed this month under a different TURN key ({_tail(k)}). "
                          "An old or rotated key is still in use somewhere; delete it in "
                          "Cloudflare → Realtime → TURN."))
            break
    return out, mine


async def _budget(session: AsyncSession, cf_bytes: int | None) -> dict:
    label, budget = "Monthly budget", settings.get("TURN_BUDGET_GB")
    if not budget:
        return _c("budget", label, "ok", "No budget limit set.")
    if await turn_over_budget(session):
        return _c("budget", label, "warn", "WebRTC paused: budget reached")
    used = cf_bytes if cf_bytes is not None else await month_bytes(session)
    return _c("budget", label, "ok", f"{used / GB:.1f} of {budget} GB budget used")


async def run_checks(session: AsyncSession, client: httpx.AsyncClient | None = None) -> dict:
    now = datetime.now(timezone.utc)
    provider = settings.get("WEBRTC_TURN_PROVIDER") or "none"
    own = client is None
    c = client or httpx.AsyncClient(timeout=10)
    checks: list[dict] = []
    try:
        if provider == "none":
            checks.append(_c("provider", "TURN provider", "skip",
                             "No TURN relay configured: WebRTC works only where direct UDP is allowed."))
        else:
            checks.append(_c("provider", "TURN provider", "ok", provider))
            checks.append(await (_credentials(c) if provider == "cloudflare" else _reachable()))
        checks.append(await _transport(session, provider))
        extra, mine = await _analytics(c, now)
        checks += extra
        checks.append(await _budget(session, mine))
    finally:
        if own:
            await c.aclose()
    return {"provider": provider, "checked_at": now.isoformat(), "checks": checks}
