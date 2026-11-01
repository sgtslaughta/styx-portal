"""Authoritative TURN usage from Cloudflare's GraphQL Analytics API.

Dataset `callsTurnUsageAdaptiveGroups`, `sum.egressBytes` (what Cloudflare bills:
bytes from its TURN servers to clients), month to date, filtered to our TURN key.
Needs CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_ANALYTICS_TOKEN (Account Analytics: Read).
Cached CACHE_S so heartbeats never hammer the API; failures keep the last value.
"""
import time
from datetime import datetime, timezone

import httpx

from app.services.settings_store import settings

URL = "https://api.cloudflare.com/client/v4/graphql"
CACHE_S = 600
QUERY = """query($acct: String!, $from: Date!, $to: Date!, $key: String) {
  viewer { accounts(filter: {accountTag: $acct}) {
    callsTurnUsageAdaptiveGroups(limit: 10000,
        filter: {date_geq: $from, date_leq: $to, keyId: $key}) { sum { egressBytes } } } } }"""

_cache: dict = {"key": None, "at": 0.0, "bytes": None, "error": None}


def configured() -> bool:
    return bool(settings.get("CLOUDFLARE_ACCOUNT_ID") and settings.get("CLOUDFLARE_ANALYTICS_TOKEN"))


def _sum(data: dict) -> int:
    accts = (((data or {}).get("data") or {}).get("viewer") or {}).get("accounts") or []
    return sum(int((g.get("sum") or {}).get("egressBytes") or 0)
               for a in accts for g in a.get("callsTurnUsageAdaptiveGroups") or [])


async def month_egress(now: datetime | None = None, client: httpx.AsyncClient | None = None) -> dict:
    """{"bytes": int | None, "error": str | None} for the current month (cached)."""
    if not configured():
        return {"bytes": None, "error": None}
    now = now or datetime.now(timezone.utc)
    key = (now.strftime("%Y-%m"), settings.get("CLOUDFLARE_ACCOUNT_ID"),
           settings.get("CLOUDFLARE_TURN_TOKEN_ID"))
    if _cache["key"] == key and time.monotonic() - _cache["at"] < CACHE_S:
        return {"bytes": _cache["bytes"], "error": _cache["error"]}
    variables = {"acct": key[1], "from": now.strftime("%Y-%m-01"), "to": now.strftime("%Y-%m-%d"),
                 "key": key[2] or None}
    headers = {"Authorization": f"Bearer {settings.get('CLOUDFLARE_ANALYTICS_TOKEN')}"}
    try:
        async with (client or httpx.AsyncClient(timeout=5)) as c:
            r = await c.post(URL, json={"query": QUERY, "variables": variables}, headers=headers)
        body = r.json()
        if r.status_code != 200 or body.get("errors"):
            raise ValueError(f"HTTP {r.status_code}: "
                             f"{(body.get('errors') or [{}])[0].get('message', 'error')}")
        _cache.update(key=key, at=time.monotonic(), bytes=_sum(body), error=None)
    except (httpx.HTTPError, ValueError) as e:
        # keep the last good value; retry after CACHE_S. Never echo the token.
        stale = _cache["key"] != key           # another month/key: last value no longer applies
        _cache.update(key=key, at=time.monotonic(), error=str(e)[:200],
                      **({"bytes": None} if stale else {}))
    return {"bytes": _cache["bytes"], "error": _cache["error"]}
