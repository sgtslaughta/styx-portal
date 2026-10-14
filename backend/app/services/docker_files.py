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
from urllib.parse import urljoin

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
_LOCATION = re.compile(r"^\s*location:\s*(\S+)", re.I | re.M)
_PROBE_URL = re.compile(r"https?://[A-Za-z0-9._:/@%+=~-]+")


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

    def probe_fetch(self, url: str, network: str, max_bytes: int, timeout_s: int = 5,
                    extra_hosts: dict | None = None,
                    allow_redirect_to: Callable[[str], bool] | None = None) -> bytes | None:
        """First `max_bytes` of the body of `url`, fetched from a throwaway container; None on failure.

        The URL is an argv entry ($1), never part of the shell string. The body travels back
        base64-encoded on stdout; wget's response headers (-S) arrive on stderr and are the only
        place redirects are read from. Any Location failing `allow_redirect_to` (or more than
        MAX_FETCH_REDIRECTS hops) discards the body.
        """
        # ponytail: busybox wget follows redirects itself, so a refused hop was still requested
        # before Styx can say no. Upgrade path: fetch hop by hop with redirects disabled
        # (e.g. a tiny curl image with --max-redirs 0).
        if not _PROBE_URL.fullmatch(url):
            raise ValueError("probe url must be plain http(s) with no shell metacharacters")
        c = self._start_probe(
            ["sh", "-c", 'wget -q -S -O - -T "$2" "$1" | head -c "$3" | base64',
             "probe", url, str(timeout_s), str(max_bytes)], network, extra_hosts)
        if c is None:
            return None
        try:
            c.wait(timeout=timeout_s + 10)
            out = c.logs(stdout=True, stderr=False)
            headers = c.logs(stdout=False, stderr=True).decode("utf-8", "replace")
            cur, hops = url, _LOCATION.findall(headers)
            if len(hops) > MAX_FETCH_REDIRECTS:
                return None
            for loc in hops:
                cur = urljoin(cur, loc)
                if allow_redirect_to is not None and not allow_redirect_to(cur):
                    return None
            return base64.b64decode(b"".join(out.split()), validate=True) or None
        except (binascii.Error, ValueError):
            return None
        except Exception:  # noqa: BLE001 - unreachable app == no body
            logger.debug("fetch of %s failed", url, exc_info=True)
            return None
        finally:
            self._rm_probe(c)

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
