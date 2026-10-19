"""Translate the Traefik file-provider route dict into k8s objects (pure)."""
import hashlib
import ipaddress
import logging
import re
from urllib.parse import urlparse

import httpx

from app.schemas import allow_list_missing, workstation_ip_allowed

logger = logging.getLogger("styx-portal")
MANAGED_LABEL = {"app.kubernetes.io/managed-by": "styx-backend"}
_TRAEFIK = "traefik.io/v1alpha1"


def k8s_name(s: str) -> str:
    """DNS-1123 label: lowercase, invalid chars -> '-', hashed when >63."""
    n = re.sub(r"[^a-z0-9-]", "-", s.lower()).strip("-")
    if len(n) > 63:
        n = f"{n[:54]}-{hashlib.sha1(s.encode()).hexdigest()[:8]}"
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
    host = u.hostname or ""
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
    else:
        ref = {"name": host, "port": port}
    if u.scheme == "https":
        ref["scheme"] = "https"
    if lb.get("serversTransport"):
        ref["serversTransport"] = k8s_name(lb["serversTransport"])
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
