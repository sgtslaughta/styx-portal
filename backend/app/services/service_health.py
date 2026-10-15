"""Proxied service health (spec §7): HTTP health_path for url services,
Docker container state / HEALTHCHECK for docker-local ones."""
import asyncio
import ipaddress
import logging
from datetime import datetime, timezone

import httpx
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ProxiedService, proxy_hostname, upstream_base

log = logging.getLogger(__name__)
CHECK_TIMEOUT = 5.0


# Link-local (incl. cloud metadata 169.254.169.254) and AWS's IPv6 IMDS: never
# probe these, an admin typo or a malicious upstream must not reach metadata.
_FORBIDDEN_NETS = tuple(ipaddress.ip_network(n) for n in (
    "169.254.0.0/16", "fe80::/10", "fd00:ec2::254/128"))


async def _forbidden_target(url: str) -> str | None:
    host = httpx.URL(url).host
    try:
        addrs = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None)
        except OSError:
            return None                      # unresolvable: the GET fails on its own
        addrs = {ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos}
    bad = [a for a in addrs if any(a in n for n in _FORBIDDEN_NETS)]
    return f"{host} resolves to link-local/metadata address {bad[0]}" if bad else None


def host_override(upstream_host: str | None) -> dict:
    """httpx kwargs that make a probe look like the proxied request: Host header + TLS SNI."""
    if not upstream_host:
        return {}
    return {"headers": {"Host": upstream_host}, "extensions": {"sni_hostname": upstream_host}}


async def check_url(url: str, verify: bool, transport: httpx.AsyncBaseTransport | None = None,
                    upstream_host: str | None = None) -> str:
    """One GET, never follows redirects (so it cannot be steered off-host)."""
    reason = await _forbidden_target(url)
    if reason:
        log.warning("health check refused: %s", reason)
        return "unhealthy"
    try:
        # verify=False is the per-service admin opt-in (verify_tls toggle).
        async with httpx.AsyncClient(verify=verify, timeout=CHECK_TIMEOUT,  # nosec B501
                                     follow_redirects=False, transport=transport) as c:
            r = await c.get(url, **host_override(upstream_host))
        return "healthy" if r.status_code < 400 else "unhealthy"
    except httpx.HTTPError:
        return "unhealthy"


async def _safe_check(checker, url: str, verify: bool, upstream_host: str | None = None) -> str:
    try:
        return await (checker(url, verify, upstream_host=upstream_host) if upstream_host
                      else checker(url, verify))
    except Exception:  # one bad service must never stop the pass
        log.warning("health check crashed for %s", url, exc_info=True)
        return "unhealthy"


async def _docker_check(docker, container: str) -> str:
    try:
        return await asyncio.to_thread(docker.container_health, container)
    except Exception:  # never let one docker hiccup stop the pass
        log.warning("docker health check crashed for %s", container, exc_info=True)
        return "unknown"


def _default_docker():
    from app.config import Settings
    from app.services.docker_manager import DockerManager
    return DockerManager(network_name=Settings().DOCKER_NETWORK)


async def run_health_pass(session: AsyncSession, checker=check_url, docker=None) -> int:
    rows = (await session.exec(select(ProxiedService).where(
        ProxiedService.enabled == True))).all()  # noqa: E712
    # docker-local containers sit on styx-services, which the backend is
    # deliberately not on: ask the Docker API instead of probing over HTTP.
    local = [s for s in rows if s.kind == "docker-local" and s.container]
    remote = [s for s in rows if s.kind != "docker-local" and s.health_path]
    ids = [s.id for s in local] + [s.id for s in remote]
    containers = [s.container for s in local]
    probes = [(upstream_base(s) + s.health_path, s.verify_tls, proxy_hostname(s)) for s in remote]
    await session.commit()          # end the read txn; don't hold ORM rows across awaits
    if containers and docker is None:
        docker = _default_docker()
    # Concurrent, so N slow services cost one timeout, not N.
    results = await asyncio.gather(
        *(_docker_check(docker, c) for c in containers),
        *(_safe_check(checker, u, v, h) for u, v, h in probes))
    now = datetime.now(timezone.utc)
    # Column-level UPDATE by id: a row deleted (or edited) by an admin while the
    # checks ran is skipped (0 rows) instead of failing the pass or clobbering edits.
    for sid, status in zip(ids, results):
        await session.exec(update(ProxiedService).where(ProxiedService.id == sid)
                           .values(health_status=status, health_checked_at=now))
    await session.commit()
    return len(ids)


async def health_loop(session_factory, interval: float = 30.0, checker=check_url,
                      docker=None) -> None:
    """Runs forever; swallows per-pass errors; stops only on cancellation."""
    docker = docker or _default_docker()      # lazy: no socket opened until used
    while True:
        await asyncio.sleep(interval)
        try:
            async with session_factory() as session:
                await run_health_pass(session, checker=checker, docker=docker)
        except Exception:
            log.warning("service health pass failed", exc_info=True)
