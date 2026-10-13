"""Polls proxied services' health_path (spec §7)."""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ProxiedService, upstream_base

log = logging.getLogger(__name__)
CHECK_TIMEOUT = 5.0


async def check_url(url: str, verify: bool, transport: httpx.AsyncBaseTransport | None = None
                    ) -> str:
    """One GET, never follows redirects (so it cannot be steered off-host)."""
    try:
        # verify=False is the per-service admin opt-in (verify_tls toggle).
        async with httpx.AsyncClient(verify=verify, timeout=CHECK_TIMEOUT,  # nosec B501
                                     follow_redirects=False, transport=transport) as c:
            r = await c.get(url)
        return "healthy" if r.status_code < 400 else "unhealthy"
    except httpx.HTTPError:
        return "unhealthy"


async def _safe_check(checker, url: str, verify: bool) -> str:
    try:
        return await checker(url, verify)
    except Exception:  # one bad service must never stop the pass
        log.warning("health check crashed for %s", url, exc_info=True)
        return "unhealthy"


async def run_health_pass(session: AsyncSession, checker=check_url) -> int:
    rows = (await session.exec(select(ProxiedService).where(
        ProxiedService.enabled == True))).all()  # noqa: E712
    targets = [s for s in rows if s.health_path]
    # Concurrent, so N slow services cost one timeout, not N.
    results = await asyncio.gather(*(
        _safe_check(checker, upstream_base(s) + s.health_path, s.verify_tls) for s in targets))
    now = datetime.now(timezone.utc)
    for s, status in zip(targets, results):
        s.health_status = status
        s.health_checked_at = now
        session.add(s)
    await session.commit()
    return len(targets)


async def health_loop(session_factory, interval: float = 30.0, checker=check_url) -> None:
    """Runs forever; swallows per-pass errors; stops only on cancellation."""
    while True:
        await asyncio.sleep(interval)
        try:
            async with session_factory() as session:
                await run_health_pass(session, checker=checker)
        except Exception:
            log.warning("service health pass failed", exc_info=True)
