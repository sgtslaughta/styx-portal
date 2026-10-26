"""Translate the Traefik file-provider route dict into k8s objects (pure)."""
import hashlib
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.schemas import allow_list_missing, workstation_ip_allowed

logger = logging.getLogger("styx-portal")
MANAGED_LABEL = {"app.kubernetes.io/managed-by": "styx-backend"}
_TRAEFIK = "traefik.io/v1alpha1"
_CLUSTER_SVC = re.compile(r"^([a-z0-9-]+)\.([a-z0-9-]+)\.svc(\.cluster\.local)?$")


def denied_namespaces() -> set[str]:
    cfg = Settings()
    denied = {n.strip() for n in cfg.K8S_UPSTREAM_DENY_NAMESPACES.split(",")
              if n.strip()} | {cfg.K8S_NAMESPACE}
    return denied - {cfg.K8S_INSTANCE_NAMESPACE}  # instance routes must resolve


_INTERNAL_SUFFIXES = (".svc", ".cluster.local", ".localhost")


def _bad_external(host: str) -> bool:
    """A hostname upstream (ExternalName) must never point back into the cluster."""
    if _CLUSTER_SVC.match(host):
        return False  # handled as a cross-namespace ref + denylist
    return (host == "localhost" or host.endswith(_INTERNAL_SUFFIXES)
            or ".svc." in host or not host
            or any(not label for label in host.split(".")))


_resolve = socket.getaddrinfo


def _resolves_safely(host: str) -> bool:
    """Resolve as Traefik's pod would (search domains apply: `kubernetes.default`
    expands to a cluster name). Public and LAN IPs are fine; cluster, loopback,
    link-local, unspecified and multicast are not."""
    # ponytail: DNS rebinding ceiling - checked at sync time only; a Traefik
    # egress NetworkPolicy is the full fix.
    try:
        infos = _resolve(host + ".", None)
    except OSError:
        return False
    nets = [ipaddress.ip_network(c.strip(), strict=False)
            for c in Settings().K8S_CLUSTER_CIDRS.split(",") if c.strip()]
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            return False
        if (ip.is_loopback or ip.is_link_local or ip.is_unspecified
                or ip.is_multicast or any(ip in n for n in nets)):
            return False
    return True


def _host_of(svc: dict) -> str:
    h = urlparse(svc["loadBalancer"]["servers"][0]["url"]).hostname or ""
    return h.rstrip(".").lower()


def k8s_name(s: str) -> str:
    """DNS-1123 label: lowercase, invalid chars -> '-', hashed when >63."""
    n = re.sub(r"[^a-z0-9-]", "-", s.lower()).strip("-")
    if len(n) > 63:
        n = f"{n[:54]}-{hashlib.sha1(s.encode(), usedforsecurity=False).hexdigest()[:8]}"
    return n


def _obj(api: str, kind: str, name: str, ns: str, **body) -> dict:
    return {"apiVersion": api, "kind": kind,
            "metadata": {"name": name, "namespace": ns,
                         "labels": dict(MANAGED_LABEL)},
            **body}


def _ip(host: str):
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _service_objects(name: str, svc: dict, ns: str) -> tuple[dict, list[dict]]:
    """Return (traefik service ref, extra Service/EndpointSlice objects)."""
    lb = svc["loadBalancer"]
    u = urlparse(lb["servers"][0]["url"])
    port = u.port or (443 if u.scheme == "https" else 80)
    host = (u.hostname or "").rstrip(".").lower()
    ip = _ip(host)
    extra: list[dict] = []
    if ip is not None:
        n = k8s_name(name)
        ref: dict = {"name": n, "port": port}
        extra.append(_obj("v1", "Service", n, ns, spec={
            "ports": [{"name": "http", "port": port, "targetPort": port}]}))
        ep = _obj("discovery.k8s.io/v1", "EndpointSlice", n + "-ep", ns,
                  addressType=f"IPv{ip.version}",
                  endpoints=[{"addresses": [str(ip)],
                              "conditions": {"ready": True}}],
                  ports=[{"name": "http", "port": port}])
        ep["metadata"]["labels"]["kubernetes.io/service-name"] = n
        extra.append(ep)
    elif name == "api":
        ref = {"name": "backend", "port": 8000}
    elif m := _CLUSTER_SVC.match(host):
        ref = {"name": m[1], "namespace": m[2], "port": port}
    elif "." not in host:
        ref = {"name": host, "port": port}
    else:
        n = k8s_name(name)
        ref = {"name": n, "port": port}
        extra.append(_obj("v1", "Service", n, ns, spec={
            "type": "ExternalName", "externalName": f"{host}.",
            "ports": [{"name": "http", "port": port, "targetPort": port}]}))
    if u.scheme == "https":
        ref["scheme"] = "https"
    if lb.get("serversTransport"):
        st = k8s_name(lb["serversTransport"])
        # Traefik looks a bare name up in the Service's namespace; the transport lives in ours.
        ref["serversTransport"] = (f"{ns}-{st}@kubernetescrd"
                                   if ref.get("namespace", ns) != ns else st)
    return ref, extra


def to_k8s_objects(config: dict, namespace: str) -> list[dict]:
    http = config.get("http", {})
    ns = namespace
    objs: list[dict] = []
    refs: dict[str, dict] = {}
    skipped: set[str] = set()
    if allow_list_missing():
        logger.error("k8s: WORKSTATION_ALLOW_CIDRS is required with ROUTE_BACKEND=k8s; "
                     "every IP upstream (workstation) route is skipped until it is set")
    for name, svc in http.get("services", {}).items():
        ip = _ip(urlparse(svc["loadBalancer"]["servers"][0]["url"]).hostname or "")
        if ip is not None and not workstation_ip_allowed(ip):
            # Defense in depth for rows stored before the allow-list existed.
            logger.warning("k8s: skipping service %s and its routers: upstream %s is "
                           "outside WORKSTATION_ALLOW_CIDRS", name, ip)
            skipped.add(name)
            continue
        host = _host_of(svc)
        m = _CLUSTER_SVC.match(host)
        if name != "api" and ip is None and (
                _bad_external(host)
                or (name.startswith("svc-") and "." not in host)
                or (not m and "." in host and not _resolves_safely(host))):
            logger.warning("k8s: skipping service %s and its routers: upstream "
                           "%s points into the cluster", name, host)
            skipped.add(name)
            continue
        if m and (m[2] in denied_namespaces() or (
                name.startswith("svc-") and m[2] == Settings().K8S_INSTANCE_NAMESPACE)):
            logger.warning("k8s: skipping service %s and its routers: upstream "
                           "namespace %s is denied", name, m[2])
            skipped.add(name)
            continue
        refs[name], extra = _service_objects(name, svc, ns)
        objs += extra

    for name, mw in http.get("middlewares", {}).items():
        spec = dict(mw)
        err = spec.get("errors")
        if err and err.get("service") in refs:
            spec["errors"] = {**err, "service": dict(refs[err["service"]])}
        objs.append(_obj(_TRAEFIK, "Middleware", k8s_name(name), ns, spec=spec))

    for name, t in http.get("serversTransports", {}).items():
        objs.append(_obj(_TRAEFIK, "ServersTransport", k8s_name(name), ns,
                         spec=t))

    for name, r in http.get("routers", {}).items():
        if r["service"] in skipped:
            continue
        route: dict = {"kind": "Rule", "match": r["rule"],
                       "services": [dict(refs[r["service"]])]}
        if "priority" in r:
            route["priority"] = r["priority"]
        if r.get("middlewares"):
            route["middlewares"] = [{"name": k8s_name(m)}
                                    for m in r["middlewares"]]
        objs.append(_obj(_TRAEFIK, "IngressRoute", k8s_name(name), ns, spec={
            "entryPoints": ["websecure"], "tls": {}, "routes": [route]}))
    return objs


_MANAGED_KINDS = (
    (_TRAEFIK, "IngressRoute"), (_TRAEFIK, "Middleware"),
    (_TRAEFIK, "ServersTransport"), ("v1", "Service"),
    ("discovery.k8s.io/v1", "EndpointSlice"),
)


class K8sSyncError(RuntimeError):
    """One or more objects failed to apply (already logged per object)."""


def sync_objects(client, desired: list[dict], namespace: str) -> None:
    """Apply every desired object, then prune stale managed ones.

    Prune is skipped if any apply failed (a partial desired set must not
    delete live routes); failures are logged per object and raised together.
    """
    failed = []
    for o in desired:
        try:
            client.apply(o)
        except httpx.TransportError as e:  # API down: fail fast, hold lock short
            logger.error("k8s API unreachable applying %s/%s: %r",
                         o["kind"], o["metadata"]["name"], e)
            raise K8sSyncError(f"k8s API unreachable ({e!r}); "
                               "apply aborted, prune skipped") from e
        except Exception as e:
            ref = f"{o['kind']}/{o['metadata']['name']}"
            logger.error("k8s apply failed for %s: %s", ref, e)
            failed.append(ref)
    if failed:
        raise K8sSyncError(
            f"{len(failed)}/{len(desired)} k8s applies failed, prune skipped: "
            + ", ".join(failed))
    selector = ",".join(f"{k}={v}" for k, v in MANAGED_LABEL.items())
    failed = []
    for api, kind in _MANAGED_KINDS:
        keep = {o["metadata"]["name"] for o in desired if o["kind"] == kind}
        for name in client.list_names(api, kind, namespace, selector):
            if name in keep:
                continue
            try:
                client.delete(api, kind, namespace, name)
            except Exception as e:
                logger.error("k8s prune failed for %s/%s: %s", kind, name, e)
                failed.append(f"{kind}/{name}")
    if failed:
        raise K8sSyncError("k8s prune failed for: " + ", ".join(failed))
