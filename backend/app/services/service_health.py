"""Proxied service health (spec §7): HTTP health_path for url services,
Docker container state / HEALTHCHECK for docker-local ones."""
import asyncio
import ipaddress
import logging
import socket
from datetime import datetime, timezone

import httpx
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ProxiedService, proxy_hostname, upstream_base

log = logging.getLogger(__name__)
CHECK_TIMEOUT = 5.0


# Never probe these: link-local/cloud metadata, loopback and "this host". RFC1918 LAN targets
# stay allowed (admins legitimately proxy LAN apps). Styx's own internals (docker-proxy,
# backend, frontend) are added at check time from DNS, see _internal_addrs.
_FORBIDDEN_NETS = tuple(ipaddress.ip_network(n) for n in (
    "169.254.0.0/16", "fe80::/10", "fd00:ec2::254/128",
    "127.0.0.0/8", "::1/128", "0.0.0.0/8", "::/128"))
_INTERNAL_NAMES = ("docker-proxy", "backend", "frontend")


async def _resolve(host: str) -> set:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except OSError:
        return set()
    return {ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos}


async def _internal_addrs() -> set:
    """Addresses of Styx's own compose services and of this container."""
    out: set = set()
    for name in (*_INTERNAL_NAMES, socket.gethostname()):
        out |= await _resolve(name)
    return out


def _unmap(a):
    return a.ipv4_mapped if getattr(a, "ipv4_mapped", None) else a


async def _checked(url: str) -> tuple[str | None, str | None]:
    """(refusal reason, ip to pin the connection to). Resolve once; the caller connects
    to that exact address so DNS cannot rebind between check and connect."""
    host = httpx.URL(url).host
    pin = None
    try:
        addrs = {ipaddress.ip_address(host)}
    except ValueError:
        addrs = await _resolve(host)
        if not addrs:
            return None, None                # unresolvable: the GET fails on its own
        pin = str(sorted(addrs, key=str)[0])
    addrs = {_unmap(a) for a in addrs}
    bad = [a for a in addrs if any(a in n for n in _FORBIDDEN_NETS)]
    if not bad:
        internal = await _internal_addrs()
        bad = [a for a in addrs if a in internal]
    return (f"{host} resolves to forbidden address {bad[0]}" if bad else None), pin


async def _forbidden_target(url: str) -> str | None:
    return (await _checked(url))[0]


def _pinned(url: str, pin: str | None, upstream_host: str | None) -> tuple[str, dict]:
    """Rewrite url to the checked IP, keeping Host header and TLS SNI/verification name."""
    if not pin:
        return url, host_override(upstream_host)
    u = httpx.URL(url)
    name = upstream_host or u.host
    port = f":{u.port}" if u.port else ""
    kw = host_override(name)
    kw["headers"] = {"Host": f"{name}{port}" if not upstream_host else name}
    return str(u.copy_with(host=pin)), kw


def host_override(upstream_host: str | None) -> dict:
    """httpx kwargs that make a probe look like the proxied request: Host header + TLS SNI."""
    if not upstream_host:
        return {}
    return {"headers": {"Host": upstream_host}, "extensions": {"sni_hostname": upstream_host}}


async def check_url(url: str, verify: bool, transport: httpx.AsyncBaseTransport | None = None,
                    upstream_host: str | None = None) -> str:
    """One GET, never follows redirects (so it cannot be steered off-host)."""
    reason, pin = await _checked(url)
    if reason:
        log.warning("health check refused: %s", reason)
        return "unhealthy"
    url, extra = _pinned(url, pin, upstream_host)
    try:
        # verify=False is the per-service admin opt-in (verify_tls toggle).
        async with httpx.AsyncClient(verify=verify, timeout=CHECK_TIMEOUT,  # nosec B501
                                     follow_redirects=False, transport=transport) as c:
            r = await c.get(url, **extra)
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
