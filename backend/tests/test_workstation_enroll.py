import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from app.models import WorkstationEnrollmentToken, Workstation, User


@pytest.mark.asyncio
async def test_mint_enroll_token_admin_only(client):
    r = await client.post("/api/workstations/enroll-tokens")
    assert r.status_code == 403  # CSRF check before auth


@pytest.mark.asyncio
async def test_mint_enroll_token(admin_client, session, monkeypatch, tmp_path):
    from app.services import workstations as ws_svc
    from app.services import lan_tls
    monkeypatch.setattr(ws_svc._settings, "SERVER_LAN_URL", "https://192.168.1.10")
    monkeypatch.setattr(lan_tls._settings, "LAN_CERT_DIR", str(tmp_path))
    r = await admin_client.post("/api/workstations/enroll-tokens")
    assert r.status_code == 201
    body = r.json()
    assert len(body["token"]) > 30
    assert body["lan_url_source"] == "env"
    assert "curl -fsSL" in body["lan_command"]
    assert "--token " + body["token"] in body["lan_command"]
    assert "--server https://192.168.1.10" in body["lan_command"]
    assert "/api/enroll/script" in body["lan_command"]
    # tunnel mode + no SERVER_CA_PIN → self-signed LAN cert auto-generated + pinned
    assert "--ca-pin sha256:" in body["lan_command"]
    # bootstrap fetch pins the public key so it verifies over self-signed TLS
    assert "--pinnedpubkey 'sha256//" in body["lan_command"]
    assert (tmp_path / "lan.crt").is_file()
    assert "--server https://localhost" in body["public_command"]
    assert "--ca-pin" not in body["public_command"]
    assert "--pinnedpubkey" not in body["public_command"]
    rows = (await session.exec(select(WorkstationEnrollmentToken))).all()
    assert len(rows) == 1
    assert rows[0].token_hash != body["token"]  # stored hashed


@pytest.mark.asyncio
async def test_mint_enroll_token_detected_lan_ip(admin_client, monkeypatch, tmp_path):
    from app.services import workstations as ws_svc
    from app.services import lan_tls
    monkeypatch.setattr(ws_svc._settings, "SERVER_LAN_URL", "")
    monkeypatch.setattr(ws_svc, "detect_lan_ip", lambda: "10.0.0.5")
    monkeypatch.setattr(lan_tls._settings, "LAN_CERT_DIR", str(tmp_path))
    r = await admin_client.post("/api/workstations/enroll-tokens")
    body = r.json()
    assert body["lan_url_source"] == "detected"
    assert "--server https://10.0.0.5" in body["lan_command"]
    assert "--ca-pin sha256:" in body["lan_command"]


@pytest.mark.asyncio
async def test_mint_explicit_ca_pin_wins(admin_client, monkeypatch):
    from app.services import workstations as ws_svc
    monkeypatch.setattr(ws_svc._settings, "SERVER_LAN_URL", "https://192.168.1.10")
    monkeypatch.setattr(ws_svc._settings, "SERVER_CA_PIN", "sha256:deadbeef")
    r = await admin_client.post("/api/workstations/enroll-tokens")
    assert "--ca-pin sha256:deadbeef" in r.json()["lan_command"]


@pytest.mark.asyncio
async def test_mint_enroll_token_no_lan_detection(admin_client, monkeypatch):
    from app.services import workstations as ws_svc
    monkeypatch.setattr(ws_svc._settings, "SERVER_LAN_URL", "")
    monkeypatch.setattr(ws_svc, "detect_lan_ip", lambda: None)
    r = await admin_client.post("/api/workstations/enroll-tokens")
    body = r.json()
    assert body["lan_url_source"] == "none"
    assert body["lan_command"] is None
    assert "--server https://localhost" in body["public_command"]


async def _mint(session, admin_id: str, *, expired=False, used=False) -> str:
    raw = secrets.token_urlsafe(32)
    delta = timedelta(hours=-1) if expired else timedelta(hours=24)
    session.add(WorkstationEnrollmentToken(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        created_by=admin_id,
        expires_at=datetime.now(timezone.utc) + delta,
        used_at=datetime.now(timezone.utc) if used else None))
    await session.commit()
    return raw


async def _admin_id(session) -> str:
    from sqlmodel import select as _select
    return (await session.exec(_select(User).where(User.role == "admin"))).first().id


@pytest.mark.asyncio
async def test_register_happy_path(admin_client, client, session):
    raw = await _mint(session, await _admin_id(session))
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "My-Desk.local", "lan_ip": "192.168.1.50",
        "display_server": "wayland", "gpu_info": {"vendor": "nvidia"},
        "os_info": {"distro": "ubuntu"}, "agent_version": "0.1.0"})
    assert r.status_code == 201
    body = r.json()
    assert body["subdomain"] == "my-desk-local"
    assert body["selkies_user"] == "styx"
    assert len(body["agent_token"]) > 30
    assert body["heartbeat_interval_s"] == 30
    ws = (await session.exec(select(Workstation))).first()
    assert ws.status == "pending"
    assert ws.agent_token_hash == hashlib.sha256(body["agent_token"].encode()).hexdigest()
    # token single-use
    r2 = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "x", "lan_ip": "1.2.3.4"})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_register_stores_full_system_report(client, admin_client, session):
    """One-time hardware/OS report from enroll.sh round-trips to the admin API."""
    raw = await _mint(session, await _admin_id(session))
    os_info = {
        "distro": "ubuntu", "pretty_name": "Ubuntu 24.04.4 LTS",
        "version": "24.04", "kernel": "6.17.0-29-generic", "arch": "x86_64",
        "cpu_model": "AMD Ryzen 9 8945HS", "cpu_cores": 16,
        "memory_mb": 62074, "disk_total_gb": 982, "disk_free_gb": 625,
        "mode": "seat",
    }
    gpu_info = {"vendor": "vaapi", "model": "AMD Radeon Graphics"}
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "rig", "lan_ip": "192.168.1.50",
        "display_server": "wayland", "gpu_info": gpu_info,
        "os_info": os_info, "agent_version": "0.4.1"})
    assert r.status_code == 201
    rows = (await admin_client.get("/api/workstations")).json()
    ws = next(w for w in rows if w["hostname"] == "rig")
    assert ws["os_info"] == os_info
    assert ws["gpu_info"] == gpu_info
    assert ws["agent_version"] == "0.4.1"


@pytest.mark.asyncio
async def test_register_rejects_expired_and_bogus(client, admin_client, session):
    raw = await _mint(session, await _admin_id(session), expired=True)
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "x", "lan_ip": "1.2.3.4"})
    assert r.status_code == 401
    r = await client.post("/api/enroll/register", json={
        "token": "bogus", "hostname": "x", "lan_ip": "1.2.3.4"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_subdomain_collision_appends_suffix(client, admin_client, session):
    aid = await _admin_id(session)
    for expected in ("desk", "desk-2"):
        raw = await _mint(session, aid)
        r = await client.post("/api/enroll/register", json={
            "token": raw, "hostname": "desk", "lan_ip": "192.168.1.50"})
        assert r.json()["subdomain"] == expected


@pytest.mark.asyncio
async def test_enroll_script_served(client):
    r = await client.get("/api/enroll/script")
    assert r.status_code == 200
    assert "--token" in r.text  # bash script content


@pytest.mark.asyncio
async def test_agent_py_served(client):
    r = await client.get("/api/enroll/agent.py")
    assert r.status_code == 200
    assert "def main" in r.text


@pytest.mark.asyncio
async def test_clipboard_bridge_py_served(client):
    r = await client.get("/api/enroll/clipboard_bridge.py")
    assert r.status_code == 200
    assert "bridge_decision" in r.text


def test_update_command_includes_clipboard_bridge():
    from app.services.workstations import build_update_command
    cmd = build_update_command("https://x")
    assert "clipboard_bridge.py" in cmd


@pytest.mark.asyncio
async def test_register_rejects_invalid_lan_ip(client, admin_client, session):
    raw = await _mint(session, await _admin_id(session))
    # Test invalid IP with port and path (route injection attempt)
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "desk", "lan_ip": "192.168.1.50:9999/evil"})
    assert r.status_code == 422
    # Test other invalid formats
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "desk", "lan_ip": "not-an-ip"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_accepts_valid_ipv4_and_ipv6(client, admin_client, session):
    aid = await _admin_id(session)
    # Test IPv4
    raw = await _mint(session, aid)
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "desk-ipv4", "lan_ip": "192.168.1.50"})
    assert r.status_code == 201
    # Test IPv6
    raw = await _mint(session, aid)
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "desk-ipv6", "lan_ip": "::1"})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_artifact_endpoint_serves_prebuilt(client, tmp_path, monkeypatch):
    from app.services import artifacts
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies-web.tar.gz").write_bytes(b"web-dist")
    r = await client.get("/api/enroll/artifacts/selkies-web.tar.gz")
    assert r.status_code == 200
    assert r.content == b"web-dist"


@pytest.mark.asyncio
async def test_artifact_endpoint_unknown_name_404(client):
    r = await client.get("/api/enroll/artifacts/evil.tar.gz")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_artifact_endpoint_missing_prebuilt_503(client, tmp_path, monkeypatch):
    from app.services import artifacts
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    r = await client.get("/api/enroll/artifacts/wheelhouse-x86_64.tar.gz")
    assert r.status_code == 503
    assert "build_agent_artifacts" in r.json()["detail"]


@pytest.mark.asyncio
async def test_agent_file_endpoints_routed(client):
    # files that exist in ./agent today
    for name in ("agent.py", "uninstall", "engine.py", "gateway.py", "selkies_launcher.py"):
        r = await client.get(f"/api/enroll/{name}")
        assert r.status_code == 200, name
