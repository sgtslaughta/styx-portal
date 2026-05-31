import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from app.services.docker_manager import DockerManager

logger = logging.getLogger("selkies-hub")

_VIEWPORT = {"width": 1280, "height": 720}
_NAV_TIMEOUT_MS = 10000
_RENDER_WAIT_MS = 3000
_CLICK_WAIT_MS = 500
# KasmVNC/Selkies desktops only render in a secure context, so capture must hit
# the container's own HTTPS web port (conventionally 3001) — NOT the http routing
# port (3000), which serves an "insecure connection" error page when loaded
# directly. Traefik fronts the http port for browsers (secure at the edge), but
# direct in-container capture has no such edge.
_SECURE_PORT = 3001


class ScreenshotService:
    def __init__(self, cache_dir: str, docker_manager: DockerManager):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._docker = docker_manager
        self._pw = None
        self._browser = None
        self._sem = asyncio.Semaphore(2)

    def _resolve_ip(self, container_id: str) -> str | None:
        container = self._docker._client.containers.get(container_id)
        networks = container.attrs["NetworkSettings"]["Networks"]
        for net in networks.values():
            ip = net.get("IPAddress")
            if ip:
                return ip
        return None

    def _secure_endpoint(self, container_id: str, port: int, protocol: str) -> tuple[str, int]:
        """Prefer the container's HTTPS web port (3001) for capture; fall back to
        the configured routing port/protocol when 3001 isn't exposed."""
        try:
            container = self._docker._client.containers.get(container_id)
            exposed = container.attrs.get("Config", {}).get("ExposedPorts", {}) or {}
            if f"{_SECURE_PORT}/tcp" in exposed:
                return "https", _SECURE_PORT
        except Exception:
            pass
        return protocol, port

    async def _ensure_browser(self):
        if self._browser is not None:
            if self._browser.is_connected():
                return
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is None:
            self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            args=["--no-sandbox", "--ignore-certificate-errors"],
        )

    async def capture(
        self, instance_id: str, container_id: str, port: int, protocol: str = "https"
    ) -> bool:
        try:
            ip = await asyncio.to_thread(self._resolve_ip, container_id)
        except Exception:
            ip = None
        if not ip:
            return False

        protocol, port = await asyncio.to_thread(
            self._secure_endpoint, container_id, port, protocol
        )

        try:
            await self._ensure_browser()
        except Exception:
            logger.debug("screenshot: browser launch failed", exc_info=True)
            return False

        async with self._sem:
            context = await self._browser.new_context(
                ignore_https_errors=True, viewport=_VIEWPORT,
            )
            try:
                page = await context.new_page()
                await page.goto(
                    f"{protocol}://{ip}:{port}/",
                    wait_until="networkidle",
                    timeout=_NAV_TIMEOUT_MS,
                )
                await page.wait_for_timeout(_RENDER_WAIT_MS)
                try:
                    await page.mouse.click(_VIEWPORT["width"] // 2, _VIEWPORT["height"] // 2)
                    await page.wait_for_timeout(_CLICK_WAIT_MS)
                except Exception:
                    pass
                png = await page.screenshot(type="png")
                (self._cache_dir / f"{instance_id}.png").write_bytes(png)
                return True
            except Exception:
                logger.debug("screenshot: capture failed for %s", instance_id, exc_info=True)
                return False
            finally:
                await context.close()

    async def close(self):
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    def get_path(self, instance_id: str) -> Path | None:
        path = self._cache_dir / f"{instance_id}.png"
        if path.exists():
            return path
        return None
