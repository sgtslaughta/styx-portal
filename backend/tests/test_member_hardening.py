import pytest
from pydantic import ValidationError

from app.models import ServiceTemplate, User
from app.schemas import WorkstationHeartbeatRequest, WorkstationRegisterRequest


@pytest.mark.parametrize("ip", ["127.0.0.1", "::1", "0.0.0.0", "169.254.169.254",
                                "224.0.0.1", "fe80::1"])
def test_lan_ip_rejects_loopback_linklocal_and_special(ip):
    with pytest.raises(ValidationError):
        WorkstationRegisterRequest(token="t", hostname="h", lan_ip=ip)
    with pytest.raises(ValidationError):
        WorkstationHeartbeatRequest(lan_ip=ip)


def test_lan_ip_accepts_private_lan():
    assert WorkstationRegisterRequest(token="t", hostname="h", lan_ip="192.168.1.9").lan_ip
    assert WorkstationHeartbeatRequest(lan_ip="10.0.0.4").lan_ip == "10.0.0.4"


async def test_members_do_not_see_env_of_templates_they_do_not_own(member_client, session):
    from sqlmodel import select
    me = (await session.exec(select(User).where(User.username == "member"))).first()
    session.add(ServiceTemplate(name="shared-t", display_name="s", image="x", shared=True, owner_id=None,
                                env_vars={"TOKEN": "s3cret"}))
    session.add(ServiceTemplate(name="mine", display_name="m", image="x", owner_id=me.id,
                                env_vars={"MINE": "ok"}))
    await session.commit()
    rows = {t["name"]: t for t in (await member_client.get("/api/templates")).json()}
    assert rows["shared-t"]["env_vars"] == {}
    assert rows["mine"]["env_vars"] == {"MINE": "ok"}
    tid = rows["shared-t"]["id"]
    assert (await member_client.get(f"/api/templates/{tid}")).json()["env_vars"] == {}


async def test_admin_still_sees_env(admin_client, session):
    session.add(ServiceTemplate(name="shared-t", display_name="s", image="x", shared=True, env_vars={"A": "b"}))
    await session.commit()
    rows = {t["name"]: t for t in (await admin_client.get("/api/templates")).json()}
    assert rows["shared-t"]["env_vars"] == {"A": "b"}


def test_dev_cors_origin_needs_explicit_flag():
    from app.config import Settings
    from app.main import cors_origins
    base = dict(DOMAIN="x.test", COOKIE_SECURE=False)
    assert "http://localhost:5173" not in cors_origins(Settings(**base, DEV_CORS=False))
    assert "http://localhost:5173" in cors_origins(Settings(**base, DEV_CORS=True))
    assert "http://localhost:5173" not in cors_origins(Settings(DOMAIN="x.test", COOKIE_SECURE=True, DEV_CORS=True))


def test_lan_ip_outside_allow_cidrs_rejected(monkeypatch):
    from app import schemas
    monkeypatch.setattr(schemas._settings, "WORKSTATION_ALLOW_CIDRS", "192.168.1.0/24")
    for ip in ("10.43.0.1", "10.42.1.5"):
        with pytest.raises(ValidationError, match="allowed workstation network"):
            WorkstationRegisterRequest(token="t", hostname="h", lan_ip=ip)
        with pytest.raises(ValidationError, match="allowed workstation network"):
            WorkstationHeartbeatRequest(lan_ip=ip)
    assert WorkstationRegisterRequest(token="t", hostname="h", lan_ip="192.168.1.50").lan_ip
    assert WorkstationHeartbeatRequest(lan_ip="192.168.1.50").lan_ip == "192.168.1.50"


def test_allow_cidrs_empty_default_allows():
    from app import schemas
    from app.config import Settings
    assert Settings.model_fields["WORKSTATION_ALLOW_CIDRS"].default == ""
    assert schemas._settings.WORKSTATION_ALLOW_CIDRS == ""
    assert WorkstationRegisterRequest(token="t", hostname="h", lan_ip="10.43.0.1").lan_ip
