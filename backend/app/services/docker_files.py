"""Container file archive access and throwaway HTTP probes (mixin for DockerManager)."""
import base64
import binascii
import io
import logging
import posixpath
import re
import tarfile
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

import docker
import docker.errors

from app.config import Settings

logger = logging.getLogger("styx-portal")


# Untrusted (container-sourced) archive streams: a single file is capped at
# 1 MiB; the raw tar stream (headers + padding) at 2 MiB.
_FILE_CAP = 1024 * 1024
_STREAM_CAP = 2 * 1024 * 1024


def _join_capped(stream) -> bytes:
    buf = io.BytesIO()
    for chunk in stream:
        buf.write(chunk)
        if buf.tell() > _STREAM_CAP:
            raise ValueError("archive stream exceeds 2 MiB cap")
    return buf.getvalue()

MAX_FETCH_REDIRECTS = 3
_HEADER_ROOM = 16384          # response headers ride in the same capped stream as the body
_HOST = re.compile(r"[A-Za-z0-9.-]+")
_REQ_PATH = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=:@%/?-]*")
_PROBE_URL = re.compile(r"https?://[A-Za-z0-9._:/@%+=~-]+")


def _build_request(url: str) -> tuple[str, str, int] | None:
    """(request text, host, port) for a plain-http URL, or None if anything looks off."""
    try:
        p = urlsplit(url)
        port = 80 if p.port is None else p.port
        host = p.hostname or ""
    except ValueError:
        return None
    if (p.scheme != "http" or "@" in p.netloc or not _HOST.fullmatch(host)
            or not 1 <= port <= 65535):
        return None
    target = (p.path or "/") + ("?" + p.query if p.query else "")
    if not _REQ_PATH.fullmatch(target):
        return None
    hdr_host = host if port == 80 else f"{host}:{port}"
    text = (f"GET {target} HTTP/1.0\r\nHost: {hdr_host}\r\nUser-Agent: styx-favicon\r\n"
            "Accept: */*\r\nConnection: close\r\n\r\n")
    return text, host, port


def _parse_response(raw: bytes) -> tuple[int, dict[str, str], bytes] | None:
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.decode("latin-1").split("\r\n")
    m = re.fullmatch(r"HTTP/1\.[01] (\d{3})(?: .*)?", lines[0])
    if not m:
        return None
    headers: dict[str, str] = {}
    for ln in lines[1:]:
        k, colon, v = ln.partition(":")
        if colon:
            headers.setdefault(k.strip().lower(), v.strip())
    return int(m.group(1)), headers, body


FETCH_SCRIPT = '{ printf "%s" "$1"; sleep "$2"; } | nc -w "$2" "$3" "$4" | head -c "$5" | base64'
_CHUNK_SIZE = re.compile(rb"([0-9A-Fa-f]{1,8})[ \t]*(?:;[^\r\n]*)?")


def _dechunk(body: bytes) -> bytes:
    """Decode a chunked body; a malformed one yields b"" (treated as no body)."""
    out, pos = bytearray(), 0
    while True:
        end = body.find(b"\r\n", pos)
        if end < 0:
            return b""
        # Plain hex only: int() alone accepts "-6" / "+5" / "0x5", and a negative size moves pos
        # backwards (an endless loop on a hostile app's body).
        m = _CHUNK_SIZE.fullmatch(body[pos:end])
        if not m:
            return b""
        size = int(m.group(1), 16)
        if size == 0:
            return bytes(out)
        chunk = body[end + 2:end + 2 + size]
        if len(chunk) < size:       # cut off by the size cap: keep what arrived
            return bytes(out + chunk)
        out += chunk
        pos = end + 2 + size + 2


class ContainerFilesMixin:
    """Needs `self._client` (a docker.DockerClient)."""

    def read_file(self, container: str, path: str) -> tuple[bytes, tarfile.TarInfo] | None:
        """(bytes, TarInfo) of one regular file inside a container, or None.

        None when the path is missing, is not a single regular-file member
        (symlink, hardlink, dir, ...), or the archive is empty. Raises
        ValueError when the stream or the file exceeds the size caps.
        """
        try:
            stream, _ = self._client.containers.get(container).get_archive(path)
        except docker.errors.NotFound:
            return None
        raw = _join_capped(stream)
        try:
            tf = tarfile.open(fileobj=io.BytesIO(raw))
            members = tf.getmembers()
        except tarfile.TarError as e:
            raise ValueError(f"malformed archive for {path}") from e
        if len(members) != 1 or not members[0].isreg():
            return None
        info = members[0]
        if info.size > _FILE_CAP:
            raise ValueError(f"{path} exceeds 1 MiB cap")
        return tf.extractfile(info).read(), info

    def write_file(self, container: str, path: str, data: bytes, like: tarfile.TarInfo) -> None:
        """Replace one file, keeping the original mode/uid/gid of `like`."""
        info = tarfile.TarInfo(posixpath.basename(path))
        info.size = len(data)
        info.mode = like.mode
        info.uid = like.uid
        info.gid = like.gid
        info.mtime = int(time.time())
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            tf.addfile(info, io.BytesIO(data))
        self._client.containers.get(container).put_archive(
            posixpath.dirname(path), buf.getvalue())

    def _start_probe(self, cmd: list[str], network: str, extra_hosts: dict | None = None):
        """Create + start the hardened throwaway container; returns it (None if it couldn't run)."""
        image = Settings().MOUNT_PROBE_IMAGE
        c = None
        try:
            try:
                self._client.images.get(image)
            except docker.errors.ImageNotFound:
                self._client.images.pull(image)
            c = self._client.containers.create(
                image, cmd,
                network=network, read_only=True, user="65534:65534", cap_drop=["ALL"], mem_limit="32m", pids_limit=32,
                security_opt=["no-new-privileges"], labels={"styx.probe": "true"},
                extra_hosts=extra_hosts)
            c.start()
        except Exception as e:  # noqa: BLE001 - the probe itself could not run
            logger.warning("Couldn't run the probe image %s: %s", image, e)
            self._rm_probe(c)
            return None
        return c

    def probe_http(self, url: str, network: str, timeout_s: int = 5,
                   extra_hosts: dict | None = None) -> int:
        """HTTP status of `url` fetched from a throwaway container on `network`; 0 on failure."""
        if not _PROBE_URL.fullmatch(url):
            raise ValueError("probe url must be plain http(s) with no shell metacharacters")
        c = self._start_probe(["wget", "-q", "-S", "-O", "/dev/null", "-T", str(timeout_s), url],
                              network, extra_hosts)
        if c is None:
            return -1
        try:
            c.wait(timeout=timeout_s + 10)
            out = c.logs(stdout=True, stderr=True).decode("utf-8", "replace")
            # busybox wget follows redirects and prints every hop; the first
            # status line is the app's own answer (3xx counts as up).
            codes = re.findall(r"HTTP/1\.[01] (\d{3})", out)
            return int(codes[0]) if codes else 0
        except Exception:  # noqa: BLE001 - unreachable app == status 0
            logger.debug("probe of %s failed", url, exc_info=True)
            return 0
        finally:
            self._rm_probe(c)

    def _run_probe(self, cmd: list[str], network: str, extra_hosts: dict | None,
                   timeout_s: int) -> bytes | None:
        """stdout of one hardened throwaway container run (always removed); None on any failure."""
        c = self._start_probe(cmd, network, extra_hosts)
        if c is None:
            return None
        try:
            c.wait(timeout=timeout_s + 10)
            return c.logs(stdout=True, stderr=False)
        except Exception:  # noqa: BLE001 - unreachable app == no body
            logger.debug("probe run failed", exc_info=True)
            return None
        finally:
            self._rm_probe(c)

    def probe_fetch(self, url: str, network: str, max_bytes: int, timeout_s: int = 5,
                    extra_hosts: dict | None = None,
                    allow_redirect_to: Callable[[str], bool] | None = None,
                    with_url: bool = False) -> bytes | tuple[bytes, str] | None:
        """First `max_bytes` of the body of `url` over plain http from a throwaway container.

        Styx makes every hop itself: the request is built here from one urlsplit of the URL, sent
        by `nc` in a fresh container, and the raw response is parsed here. A redirect is followed
        (max MAX_FETCH_REDIRECTS) only if `allow_redirect_to` accepts it, and that is decided
        before any request for it exists. Every value reaches the container as a positional
        argument, never inside the shell string. None on any failure.
        """
        # ponytail: ceiling = HTTP/1.0 only, no TLS on this path (docker-local apps on
        # styx-services speak plain http). Upgrade path: a curl image with --max-redirs 0.
        cur = url
        for hop in range(MAX_FETCH_REDIRECTS + 1):
            req = _build_request(cur)
            if req is None:
                return None
            text, host, port = req
            out = self._run_probe(
                # stdin stays open: busybox nc half-closes on EOF and Kestrel apps then drop the
                # request. ponytail: each hop takes the full timeout; fine for a background fetch.
                ["sh", "-c", FETCH_SCRIPT,
                 "probe", text, str(timeout_s), host, str(port), str(max_bytes + _HEADER_ROOM)],
                network, extra_hosts, timeout_s)
            try:
                raw = base64.b64decode(b"".join((out or b"").split()), validate=True)
            except (binascii.Error, ValueError):
                return None
            parsed = _parse_response(raw)
            if parsed is None:
                return None
            status, headers, body = parsed
            if 300 <= status < 400 and "location" in headers:
                nxt = urljoin(cur, headers["location"])
                if allow_redirect_to is None or not allow_redirect_to(nxt):
                    return None
                cur = nxt
                continue
            if not 200 <= status < 300:
                return None
            if headers.get("transfer-encoding", "").lower() == "chunked":
                body = _dechunk(body)
            if not body:
                return None
            return (body[:max_bytes], cur) if with_url else body[:max_bytes]  # cur = after redirects
        return None

    @staticmethod
    def _rm_probe(c) -> None:
        if c is not None:
            try:
                c.remove(force=True)
            except Exception:  # noqa: BLE001
                logger.warning("could not remove probe container", exc_info=True)

    def remove_probe_containers(self) -> int:
        """Force-remove probe containers left behind by a crash."""
        n = 0
        for c in self._client.containers.list(all=True, filters={"label": "styx.probe=true"}):
            self._rm_probe(c)
            n += 1
        return n

    def container_labels(self, container: str) -> dict:
        return self._client.containers.get(container).labels or {}

    def container_logs(self, container: str, tail: int = 20) -> str:
        raw = self._client.containers.get(container).logs(tail=tail)
        return raw.decode("utf-8", "replace")
