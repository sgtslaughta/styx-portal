import io
import tarfile
from unittest.mock import MagicMock, patch

import docker.errors
import pytest

from app.services.docker_manager import DockerManager


def _tar(name: str, data: bytes, typ: bytes = tarfile.REGTYPE, link: str = "") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        ti = tarfile.TarInfo(name)
        ti.type = typ
        ti.linkname = link
        ti.size = len(data) if typ == tarfile.REGTYPE else 0
        ti.mode = 0o640
        ti.uid = 911
        ti.gid = 911
        t.addfile(ti, io.BytesIO(data) if typ == tarfile.REGTYPE else None)
    return buf.getvalue()


@pytest.fixture
def dm_client():
    with patch("app.services.docker_manager.docker.DockerClient") as cls:
        client = MagicMock()
        cls.return_value = client
        yield DockerManager(network_name="styx-portal"), client


def _container(client, container=None):
    container = container or MagicMock()
    client.containers.get.return_value = container
    return container


def test_read_file_returns_bytes_and_info(dm_client):
    dm, client = dm_client
    c = _container(client)
    c.get_archive.return_value = (iter([_tar("config.xml", b"<Config/>")]), {})
    data, info = dm.read_file("sonarr", "/config/config.xml")
    assert data == b"<Config/>"
    assert (info.uid, info.gid, info.mode) == (911, 911, 0o640)
    client.containers.get.assert_called_with("sonarr")
    c.get_archive.assert_called_once_with("/config/config.xml")


def test_read_missing_returns_none(dm_client):
    dm, client = dm_client
    c = _container(client)
    c.get_archive.side_effect = docker.errors.NotFound("x")
    assert dm.read_file("sonarr", "/nope") is None


def test_read_symlink_member_returns_none(dm_client):
    dm, client = dm_client
    c = _container(client)
    c.get_archive.return_value = (
        iter([_tar("config.xml", b"", typ=tarfile.SYMTYPE, link="/etc/shadow")]), {})
    assert dm.read_file("sonarr", "/config/config.xml") is None


def test_read_hardlink_member_returns_none(dm_client):
    dm, client = dm_client
    c = _container(client)
    c.get_archive.return_value = (
        iter([_tar("config.xml", b"", typ=tarfile.LNKTYPE, link="/etc/shadow")]), {})
    assert dm.read_file("sonarr", "/config/config.xml") is None


def test_read_oversize_stream_raises(dm_client):
    dm, client = dm_client
    c = _container(client)
    chunks = [b"\0" * (1024 * 1024)] * 3  # 3 MiB raw stream, over the 2 MiB cap
    c.get_archive.return_value = (iter(chunks), {})
    with pytest.raises(ValueError, match="2 MiB"):
        dm.read_file("sonarr", "/config/config.xml")


def test_write_file_preserves_owner(dm_client):
    dm, client = dm_client
    c = _container(client)
    like = tarfile.TarInfo("config.xml")
    like.uid, like.gid, like.mode = 911, 911, 0o640
    dm.write_file("sonarr", "/config/config.xml", b"<Config>x</Config>", like)
    client.containers.get.assert_called_with("sonarr")
    dest, blob = c.put_archive.call_args.args
    assert dest == "/config"
    ti = tarfile.open(fileobj=io.BytesIO(blob)).getmember("config.xml")
    assert (ti.uid, ti.gid, ti.mode, ti.size) == (911, 911, 0o640, len(b"<Config>x</Config>"))


def test_container_labels_returns_dict(dm_client):
    dm, client = dm_client
    c = _container(client)
    c.labels = {"styx.managed": "true"}
    assert dm.container_labels("sonarr") == {"styx.managed": "true"}


def test_container_labels_none_becomes_empty(dm_client):
    dm, client = dm_client
    c = _container(client)
    c.labels = None
    assert dm.container_labels("sonarr") == {}


def test_container_logs_tail_and_decode(dm_client):
    dm, client = dm_client
    c = _container(client)
    c.logs.return_value = b"line1\nline2\xff\n"
    assert dm.container_logs("sonarr") == "line1\nline2�\n"
    c.logs.assert_called_once_with(tail=20)


def test_restart_container_uses_30s_timeout(dm_client):
    dm, client = dm_client
    c = _container(client)
    dm.restart_container("sonarr")
    c.restart.assert_called_once_with(timeout=30)


def test_read_file_truncated_tar_is_value_error(dm_client):
    dm, client = dm_client
    good = _tar("c.xml", b"x" * 2000)
    container = _container(client)
    container.get_archive.return_value = (iter([good[:700]]), {})
    with pytest.raises(ValueError):
        dm.read_file("c", "/c.xml")
