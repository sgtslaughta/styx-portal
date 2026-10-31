"""Periodic thumbnail capture of enabled proxied services (url + docker-local, no Docker API needed)."""
import asyncio
import logging

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ProxiedService, upstream_base

log = logging.getLogger(__name__)


async def capture_services_pass(session: AsyncSession, screenshots) -> None:
    rows = (await session.exec(select(ProxiedService).where(
        ProxiedService.enabled == True))).all()  # noqa: E712
    for s in rows:
        url = upstream_base(s)
        if not url:
            continue
        try:
            await screenshots.capture_url(s.id, url)
        except Exception:
            log.debug("service thumbnail failed for %s", s.id, exc_info=True)


async def service_thumbnail_loop(session_factory, cache_dir: str, every_s: int = 300) -> None:
    """Capture every enabled proxied service now and every `every_s` (works on k8s: no Docker)."""
    from app.services.screenshot import ScreenshotService

    screenshots = ScreenshotService(cache_dir=cache_dir, docker_manager=None)
    try:
        while True:
            try:
                async with session_factory() as session:
                    await capture_services_pass(session, screenshots)
            except Exception:
                log.debug("service thumbnail pass failed", exc_info=True)
            await asyncio.sleep(every_s)
    finally:
        await screenshots.close()
