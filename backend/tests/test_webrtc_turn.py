from datetime import datetime, timezone

import pytest
from sqlmodel import select

from app.models import SystemSetting, TurnUsage
from app.services.settings_store import SettingsService
from app.services.turn_usage import record_turn_usage, usage_report
from app.services.ws_settings import resolve_stream_settings, supports_webrtc
from tests.test_workstation_agent_api import _auth, _make_ws

SYS = {"WORKSTATION_IDLE_TIMEOUT_S": 900, "WORKSTATION_IDLE_WARN_LEAD_S": 60,
       "WORKSTATION_IDLE_TIMEOUT_ENABLED": True, "WORKSTATION_SEAT_WIDTH": 2560,
       "WORKSTATION_SEAT_HEIGHT": 1440, "WORKSTATION_TRANSPORT": "websockets",
       "WEBRTC_MAX_SESSION_H": 8, "WEBRTC_TURN_PROVIDER": "none"}
CF = {**SYS, "WEBRTC_TURN_PROVIDER": "cloudflare", "CLOUDFLARE_TURN_TOKEN_ID": "id",
      "CLOUDFLARE_TURN_API_TOKEN": "tok"}


def row(svc, key):
    return next(s for g in svc.effective() for s in g["settings"] if s["key"] == key)


async def test_secret_roundtrip_encrypted_and_hidden(session):
    svc = SettingsService()
    await svc.set(session, "TURN_PASSWORD", "hunter2", "u")
    await session.commit()
    stored = await session.get(SystemSetting, "TURN_PASSWORD")
    assert "hunter2" not in str(stored.value)
    assert svc.get("TURN_PASSWORD") == "hunter2"
    r = row(svc, "TURN_PASSWORD")
    assert r["value"] is None and r["is_set"] is True
    assert "hunter2" not in str(svc.effective())
    svc2 = SettingsService()
    await svc2.reload(session)
    assert svc2.get("TURN_PASSWORD") == "hunter2"
    await svc.set(session, "TURN_PASSWORD", "", "u")
    assert svc.get("TURN_PASSWORD") == "" and row(svc, "TURN_PASSWORD")["is_set"] is False
    await session.commit()
    assert await session.get(SystemSetting, "TURN_PASSWORD") is None


async def test_enum_str_validation(session):
    svc = SettingsService()
    with pytest.raises(ValueError):
        await svc.set(session, "WORKSTATION_TRANSPORT", "quic", None)
    with pytest.raises(ValueError):
        await svc.set(session, "TURN_HOST", "x" * 513, None)
    with pytest.raises(ValueError):
        await svc.set(session, "TURN_USD_PER_GB", "abc", None)
    await svc.set(session, "TURN_USD_PER_GB", "0.07", None)
    assert row(svc, "WORKSTATION_TRANSPORT")["choices"] == ["websockets", "webrtc"]
    assert row(svc, "TURN_PORT")["value"] == 3478


async def test_secret_not_in_audit_or_patch_response(admin_client, session):
    r = await admin_client.patch("/api/system-settings", json={"TURN_SHARED_SECRET": "s3cr3t!"})
    assert r.status_code == 200 and "s3cr3t!" not in r.text
    from app.models import AuditLog
    logs = (await session.exec(select(AuditLog))).all()
    assert "s3cr3t!" not in str([x.__dict__ for x in logs])


def test_supports_webrtc():
    assert supports_webrtc("0.9.30") and supports_webrtc("0.10.0")
    assert not supports_webrtc("0.9.29") and not supports_webrtc(None)


def test_old_agent_unchanged():
    eff = resolve_stream_settings({"transport": "webrtc"}, CF, "0.9.29")
    assert "turn" not in eff and "max_session_s" not in eff


def test_transport_resolution_and_turn():
    eff = resolve_stream_settings(None, CF, "0.9.30")
    assert eff["transport"] == "websockets" and "turn" not in eff
    assert eff["max_session_s"] == 8 * 3600
    eff = resolve_stream_settings({"transport": "inherit"}, {**CF, "WORKSTATION_TRANSPORT": "webrtc"}, "0.9.30")
    assert eff["transport"] == "webrtc"
    assert eff["turn"] == {"provider": "cloudflare", "token_id": "id", "api_token": "tok"}
    eff = resolve_stream_settings({"transport": "webrtc"}, CF, "0.9.30")
    assert eff["transport"] == "webrtc" and "turn" in eff
    eff = resolve_stream_settings({"transport": "webrtc"}, {**CF, "CLOUDFLARE_TURN_API_TOKEN": ""}, "0.9.30")
    assert "turn" not in eff


def test_generic_turn_variants():
    g = {**SYS, "WEBRTC_TURN_PROVIDER": "generic", "TURN_HOST": "t.example", "TURN_PORT": 3478,
         "TURN_PROTOCOL": "udp", "TURN_TLS": False}
    ss = {"transport": "webrtc"}
    assert "turn" not in resolve_stream_settings(ss, g, "0.9.30")
    t = resolve_stream_settings(ss, {**g, "TURN_SHARED_SECRET": "k"}, "0.9.30")["turn"]
    assert t == {"provider": "generic", "host": "t.example", "port": 3478,
                 "protocol": "udp", "tls": False, "shared_secret": "k"}
    t = resolve_stream_settings(ss, {**g, "TURN_USERNAME": "u", "TURN_PASSWORD": "p"}, "0.9.30")["turn"]
    assert t["username"] == "u" and t["password"] == "p" and "shared_secret" not in t
    assert "turn" not in resolve_stream_settings(ss, {**g, "TURN_USERNAME": "u"}, "0.9.30")


async def test_heartbeat_meters_turn_bytes(client, session):
    ws = await _make_ws(session, status="online")
    ws.agent_version = "0.9.30"
    ws.occupied_by = ws.created_by
    session.add(ws)
    await session.commit()
    for b in (1000, 500, -5, "x", True, 0, None):
        r = await client.post("/api/agent/heartbeat", json={"health": {"turn_bytes": b,
                              "active_connections": 1}}, headers=_auth())
        assert r.status_code == 200
    assert r.json()["stream_settings"]["transport"] == "websockets"
    rows = (await session.exec(select(TurnUsage))).all()
    assert len(rows) == 1 and rows[0].bytes == 1500 and rows[0].user_id == ws.created_by


async def test_unattributed_row_accumulates(session):
    ws = await _make_ws(session, status="online")
    now = datetime(2026, 11, 2, tzinfo=timezone.utc)
    await record_turn_usage(session, ws, 10, now)
    await session.commit()
    await record_turn_usage(session, ws, 5, now)
    await session.commit()
    rows = (await session.exec(select(TurnUsage))).all()
    assert len(rows) == 1 and rows[0].bytes == 15 and rows[0].user_id is None


async def test_usage_report_math(session):
    ws = await _make_ws(session, status="online")
    ws.occupied_by = ws.created_by
    session.add(ws)
    await session.commit()
    sess_now = datetime(2026, 11, 11, tzinfo=timezone.utc)   # 10 days elapsed of 30
    await record_turn_usage(session, ws, 1_500_000_000_000, sess_now)   # 1500 GB
    await session.commit()
    rep = await usage_report(session, None, sess_now)
    assert rep["month"] == "2026-11" and rep["free_gb"] == 1000
    assert rep["total_bytes"] == 1_500_000_000_000
    assert rep["est_usd"] == 25.0               # 500 GB * 0.05
    assert rep["projected_bytes"] == 4_500_000_000_000
    assert rep["projected_usd"] == 175.0        # 3500 GB * 0.05
    assert rep["by_workstation"][0]["name"] == "desk"
    assert rep["by_user"][0]["bytes"] == 1_500_000_000_000
    past = await usage_report(session, "2026-10", sess_now)
    assert past["total_bytes"] == 0 and past["projected_bytes"] == 0


async def test_usage_endpoint_admin_only(member_client):
    assert (await member_client.get("/api/admin/turn-usage")).status_code in (401, 403)


async def test_usage_endpoint(admin_client):
    r = await admin_client.get("/api/admin/turn-usage")
    assert r.status_code == 200
    assert set(r.json()) == {"month", "free_gb", "usd_per_gb", "total_bytes", "est_usd",
                             "projected_bytes", "projected_usd", "by_workstation", "by_user"}
    assert (await admin_client.get("/api/admin/turn-usage?month=bad")).status_code == 400
